"""智谱 BigModel（GLM）回答适配器：`ChatModel` 的 OpenAI 兼容实现（M0-01 §5.2）。

端点 `POST {base_url}/chat/completions`，两种调用共用一个 URL，用 `stream` 字段区分：

- `complete` 一次取回完整正文；
- `stream` 走 `client.stream()`，逐行解析 SSE 分片，**收到一块 yield 一块**，不攒完再发。

`reasoning_content` 与 `content` 分开处理：只有 `content` 进入 `ChatResponse.text` /
`ChatChunk.text`，推理内容不交给用户回答。采样参数固定为官方建议值（`temperature=1`、
`top_p=0.95`、`reasoning_effort=max`），M0 的管线不覆盖；`ChatOptions` 显式给出的
`temperature` / `top_p` / `max_tokens` 仍然生效，覆盖是调用方的显式行为。

凭据只读环境变量 `GLM_API_KEY`，缺失时构造即抛 `ProviderConfigError`：不静默降级，也不在
日志里回显密钥。超时映射到 `ProviderTimeoutError`（决策要求超时走 `RAG_TIMEOUT` / 504），
其余网络与响应错误统一成 `ProviderError` 子类。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from omniread.infrastructure.providers.base import (
    ChatChunk,
    ChatMessage,
    ChatOptions,
    ChatResponse,
)
from omniread.infrastructure.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
)

GLM_API_KEY_ENV = "GLM_API_KEY"

GLM_ANSWER_MODEL = "glm-5.3-flash"
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 官方建议采样参数（M0-01 §5.2）；M0 的管线不覆盖。
GLM_TEMPERATURE = 1.0
GLM_TOP_P = 0.95
GLM_REASONING_EFFORT = "max"

# 生成比 embedding / rerank 慢，超时留足一次完整回答的时间。
DEFAULT_TIMEOUT_SECONDS = 60.0

_PROVIDER_NAME = "glm"

_SSE_DATA_PREFIX = "data:"
_SSE_DONE = "[DONE]"


def _resolve_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get(GLM_API_KEY_ENV)
    if not key:
        raise ProviderConfigError(
            f"{GLM_API_KEY_ENV} 未注入：GLM 凭据只从环境变量读，不设默认值",
            provider=_PROVIDER_NAME,
        )
    return key


class GlmChatAdapter:
    """`ChatModel` 的 GLM 实现，`model` 默认 `glm-5.3-flash`。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = GLM_BASE_URL,
        model: str = GLM_ANSWER_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = _resolve_api_key(api_key)
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout
        # 注入的 client 生命周期归调用方（测试用 MockTransport 走这条）；
        # 未注入时懒建一个，连接复用，由 aclose() 释放。
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """释放自建连接池；注入的 client 不动。"""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None, *, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": (
                GLM_TEMPERATURE
                if options is None or options.temperature is None
                else options.temperature
            ),
            "top_p": GLM_TOP_P if options is None or options.top_p is None else options.top_p,
            "reasoning_effort": GLM_REASONING_EFFORT,
            "stream": stream,
        }
        if options is not None and options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        return payload

    async def complete(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> ChatResponse:
        """非流式补全；`reasoning_content` 单独存，调用方只把 `text` 交给用户。"""
        try:
            response = await self._http().post(
                self._url,
                json=self._payload(messages, options, stream=False),
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("GLM 请求超时", provider=_PROVIDER_NAME) from exc
        except httpx.HTTPError as exc:
            # 连接失败 / DNS 失败等：不带上原始异常文本里的 URL 与主机细节。
            raise ProviderError("GLM 请求失败", provider=_PROVIDER_NAME) from exc
        self._raise_for_status(response.status_code)
        body = self._parse_json(response, context="响应")
        message = _first_message(body)
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderResponseError("GLM 响应缺 content", provider=_PROVIDER_NAME)
        reasoning = message.get("reasoning_content")
        model = body.get("model")
        return ChatResponse(
            text=content,
            model=model if isinstance(model, str) and model else self.model,
            reasoning=reasoning if isinstance(reasoning, str) else None,
        )

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        """流式补全：每个含 `content` 的分片即时 yield，reasoning 分片丢弃。

        上游未发 `data: [DONE]` 就断流，说明回答可能被截断，按响应错误处理而不是当成功。
        """
        payload = self._payload(messages, options, stream=True)
        try:
            async with self._http().stream(
                "POST", self._url, json=payload, headers=self._headers()
            ) as response:
                self._raise_for_status(response.status_code)
                saw_done = False
                async for line in response.aiter_lines():
                    data = _sse_data(line)
                    if data is None:
                        continue
                    if data == _SSE_DONE:
                        saw_done = True
                        break
                    text = _delta_content(data)
                    if text:
                        yield ChatChunk(text=text)
                if not saw_done:
                    raise ProviderResponseError(
                        "GLM 流式响应缺少 [DONE] 终止帧", provider=_PROVIDER_NAME
                    )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("GLM 请求超时", provider=_PROVIDER_NAME) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("GLM 请求失败", provider=_PROVIDER_NAME) from exc

    def _raise_for_status(self, status_code: int) -> None:
        if status_code >= 400:
            raise ProviderError(
                f"GLM 返回 HTTP {status_code}",
                provider=_PROVIDER_NAME,
                status_code=status_code,
            )

    def _parse_json(self, response: httpx.Response, *, context: str) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                f"GLM {context}不是 JSON", provider=_PROVIDER_NAME
            ) from exc
        if not isinstance(body, dict):
            raise ProviderResponseError(
                f"GLM {context}不是 JSON 对象", provider=_PROVIDER_NAME
            )
        return body


def _first_message(body: dict[str, Any]) -> dict[str, Any]:
    """取 `choices[0].message`；结构不符即响应错误。"""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError("GLM 响应缺 choices", provider=_PROVIDER_NAME)
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        raise ProviderResponseError("GLM 响应缺 message", provider=_PROVIDER_NAME)
    return message


def _sse_data(line: str) -> str | None:
    """取 SSE 行的 `data` 值；空行、注释行与非 data 行返回 None（忽略）。"""
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or not stripped.startswith(_SSE_DATA_PREFIX):
        return None
    return stripped[len(_SSE_DATA_PREFIX) :].strip()


def _delta_content(data: str) -> str:
    """解析流式分片的增量正文；`reasoning_content` 与空 delta 都返回空串。"""
    try:
        body = json.loads(data)
    except ValueError as exc:
        raise ProviderResponseError("GLM 流式分片不是 JSON", provider=_PROVIDER_NAME) from exc
    if not isinstance(body, dict):
        raise ProviderResponseError("GLM 流式分片不是 JSON 对象", provider=_PROVIDER_NAME)
    choices = body.get("choices")
    # 带 usage 的收尾分片 choices 为空，不是错误。
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    delta = first.get("delta") if isinstance(first, dict) else None
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if content is None:
        return ""
    if not isinstance(content, str):
        raise ProviderResponseError("GLM 流式分片 content 不是字符串", provider=_PROVIDER_NAME)
    return content


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "GLM_ANSWER_MODEL",
    "GLM_API_KEY_ENV",
    "GLM_BASE_URL",
    "GLM_REASONING_EFFORT",
    "GLM_TEMPERATURE",
    "GLM_TOP_P",
    "GlmChatAdapter",
]

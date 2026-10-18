"""OpenAI 兼容 `/chat/completions` 的适配器基类。

GLM 与 DeepSeek 的对话接口是同一个形状：`POST {base_url}/chat/completions`，
`choices[0].message.content`，流式走 SSE 的 `data:` 行并以 `[DONE]` 收尾。
两者只差**常量与几个采样参数**，所以协议转换写在这里一份，各自那份只放常量。

`reasoning_content` 与 `content` 分开处理：只有 `content` 进入 `ChatResponse.text` /
`ChatChunk.text`，推理内容不交给用户。

凭据只读环境变量，缺失时构造即抛 `ProviderConfigError`：不静默降级，也不在日志里回显密钥。
超时映射到 `ProviderTimeoutError`，其余网络与响应错误统一成 `ProviderError` 子类。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any, ClassVar

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

# 生成比 embedding / rerank 慢，超时留足一次完整回答的时间。检索那两侧是另一个值
# （`ali.EMBEDDING_TIMEOUT_SECONDS` = 30.0）——**两个常量不同名**，见那边的注释。
CHAT_TIMEOUT_SECONDS = 60.0

_SSE_DATA_PREFIX = "data:"
_SSE_DONE = "[DONE]"


class OpenAiCompatibleChatAdapter:
    """`ChatModel` 的 OpenAI 兼容实现。子类只提供下面这几个类属性。

    **采样参数分两层**：`default_*` 是这一家的建议值（调用方不传时用），
    `extra_payload` 是这一家特有的字段（比如 GLM 的 `reasoning_effort`）。
    调用方通过 `ChatOptions` 显式给出的 `temperature` / `top_p` / `max_tokens` 仍然生效
    ——覆盖是调用方的显式行为。
    """

    provider: ClassVar[str]
    display_name: ClassVar[str]
    api_key_env: ClassVar[str]
    default_model: ClassVar[str]
    default_base_url: ClassVar[str]
    default_temperature: ClassVar[float | None] = None
    default_top_p: ClassVar[float | None] = None
    extra_payload: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = CHAT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model or self.default_model
        self._api_key = self._resolve_api_key(api_key)
        self._url = f"{(base_url or self.default_base_url).rstrip('/')}/chat/completions"
        self._timeout = timeout
        # 注入的 client 生命周期归调用方（测试用 MockTransport 走这条）；
        # 未注入时懒建一个，连接复用，由 aclose() 释放。
        self._client = client
        self._owns_client = client is None

    @classmethod
    def _resolve_api_key(cls, api_key: str | None) -> str:
        key = api_key or os.environ.get(cls.api_key_env)
        if not key:
            raise ProviderConfigError(
                f"{cls.api_key_env} 未注入：{cls.display_name} 凭据只从环境变量读，不设默认值",
                provider=cls.provider,
            )
        return key

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
                self.default_temperature
                if options is None or options.temperature is None
                else options.temperature
            ),
            "top_p": (
                self.default_top_p if options is None or options.top_p is None else options.top_p
            ),
            "stream": stream,
        }
        payload.update(self.extra_payload)
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
            raise ProviderTimeoutError(
                f"{self.display_name} 请求超时", provider=self.provider
            ) from exc
        except httpx.HTTPError as exc:
            # 连接失败 / DNS 失败等：不带上原始异常文本里的 URL 与主机细节。
            raise ProviderError(
                f"{self.display_name} 请求失败", provider=self.provider
            ) from exc
        self._raise_for_status(response.status_code)
        body = self._parse_json(response, context="响应")
        message = self._first_message(body)
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderResponseError(
                f"{self.display_name} 响应缺 content", provider=self.provider
            )
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
                    text = self._delta_content(data)
                    if text:
                        yield ChatChunk(text=text)
                if not saw_done:
                    raise ProviderResponseError(
                        f"{self.display_name} 流式响应缺少 [DONE] 终止帧", provider=self.provider
                    )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self.display_name} 请求超时", provider=self.provider
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self.display_name} 请求失败", provider=self.provider
            ) from exc

    def _raise_for_status(self, status_code: int) -> None:
        if status_code >= 400:
            raise ProviderError(
                f"{self.display_name} 返回 HTTP {status_code}",
                provider=self.provider,
                status_code=status_code,
            )

    def _parse_json(self, response: httpx.Response, *, context: str) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                f"{self.display_name} {context}不是 JSON", provider=self.provider
            ) from exc
        if not isinstance(body, dict):
            raise ProviderResponseError(
                f"{self.display_name} {context}不是 JSON 对象", provider=self.provider
            )
        return body

    def _first_message(self, body: dict[str, Any]) -> dict[str, Any]:
        """取 `choices[0].message`；结构不符即响应错误。"""
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError(
                f"{self.display_name} 响应缺 choices", provider=self.provider
            )
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        if not isinstance(message, dict):
            raise ProviderResponseError(
                f"{self.display_name} 响应缺 message", provider=self.provider
            )
        return message

    def _delta_content(self, data: str) -> str:
        """解析流式分片的增量正文；`reasoning_content` 与空 delta 都返回空串。"""
        try:
            body = json.loads(data)
        except ValueError as exc:
            raise ProviderResponseError(
                f"{self.display_name} 流式分片不是 JSON", provider=self.provider
            ) from exc
        if not isinstance(body, dict):
            raise ProviderResponseError(
                f"{self.display_name} 流式分片不是 JSON 对象", provider=self.provider
            )
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
            raise ProviderResponseError(
                f"{self.display_name} 流式分片 content 不是字符串", provider=self.provider
            )
        return content


def _sse_data(line: str) -> str | None:
    """取 SSE 行的 `data` 值；空行、注释行与非 data 行返回 None（忽略）。"""
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or not stripped.startswith(_SSE_DATA_PREFIX):
        return None
    return stripped[len(_SSE_DATA_PREFIX) :].strip()


__all__ = ["CHAT_TIMEOUT_SECONDS", "OpenAiCompatibleChatAdapter"]

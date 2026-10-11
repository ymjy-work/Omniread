"""DeepSeek 适配器：这一家特有的东西。

协议解析本身与 GLM 共用 `openai_compat` 的基类（那部分在 `test_chat_providers.py` 覆盖），
所以这里只钉三件：**端点与模型、环境变量名、以及「不替调用方选采样参数」**。

全程走 `httpx.MockTransport`，一次真实调用都不发；凭据用测试串，不读环境变量。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from omniread.infrastructure.providers import (
    ChatModel,
    DeepSeekChatAdapter,
    ProviderConfigError,
    ProviderError,
    ProviderTimeoutError,
)
from omniread.infrastructure.providers.base import ChatMessage, ChatOptions
from omniread.infrastructure.providers.deepseek import (
    DEEPSEEK_API_KEY_ENV,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
)

TEST_KEY = "test-key-not-a-real-credential"

MESSAGES = [ChatMessage(role="user", content="那她后来呢？")]


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok(content: str = "改写后的问句") -> httpx.Response:
    return httpx.Response(
        200,
        json={"model": DEEPSEEK_MODEL, "choices": [{"message": {"content": content}}]},
    )


def test_adapter_satisfies_the_chat_model_protocol() -> None:
    """形参声明即校验：改写链只依赖 `ChatModel` 这个协议，实现必须满足它。"""
    adapter = DeepSeekChatAdapter(api_key=TEST_KEY, client=_client(lambda request: _ok()))

    assert isinstance(adapter, ChatModel)


def test_missing_credential_fails_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺凭据构造即失败——**这一层不做降级**。

    「缺凭据只降级」是装配处的口径（`api/app.py::build_rewriter` 自己 try 住），
    适配器只管把自己构造失败这件事说清楚。
    """
    monkeypatch.delenv(DEEPSEEK_API_KEY_ENV, raising=False)

    with pytest.raises(ProviderConfigError):
        DeepSeekChatAdapter()


async def test_credential_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEEPSEEK_API_KEY_ENV, TEST_KEY)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return _ok()

    adapter = DeepSeekChatAdapter(client=_client(handler))
    assert adapter.model == DEEPSEEK_MODEL
    await adapter.complete(MESSAGES)

    assert seen["auth"] == f"Bearer {TEST_KEY}"


async def test_request_shape() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return _ok()

    adapter = DeepSeekChatAdapter(api_key=TEST_KEY, client=_client(handler))
    response = await adapter.complete(MESSAGES, ChatOptions(temperature=0.0))

    assert seen["url"] == f"{DEEPSEEK_BASE_URL}/chat/completions"
    assert seen["body"]["model"] == DEEPSEEK_MODEL
    assert seen["body"]["messages"] == [{"role": "user", "content": "那她后来呢？"}]
    assert seen["body"]["stream"] is False
    # 采样参数由调用方给：改写要的是确定性，这个值不该由适配器替它选。
    assert seen["body"]["temperature"] == 0.0
    # `reasoning_effort` 是 GLM 特有的字段，不该出现在这一家的请求体里。
    assert "reasoning_effort" not in seen["body"]
    assert seen["auth"] == f"Bearer {TEST_KEY}"
    assert response.text == "改写后的问句"
    assert response.model == DEEPSEEK_MODEL


async def test_timeout_maps_to_provider_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("读超时", request=request)

    adapter = DeepSeekChatAdapter(api_key=TEST_KEY, client=_client(handler))

    with pytest.raises(ProviderTimeoutError):
        await adapter.complete(MESSAGES)


async def test_http_error_maps_to_provider_error() -> None:
    adapter = DeepSeekChatAdapter(
        api_key=TEST_KEY, client=_client(lambda request: httpx.Response(503, json={}))
    )

    with pytest.raises(ProviderError):
        await adapter.complete(MESSAGES)

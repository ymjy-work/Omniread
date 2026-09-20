"""回答 provider 单测：GLM 适配器的协议解析与错误映射、假 chat provider 的确定性。

全程走 `httpx.MockTransport`，一次真实 GLM 调用都不发；凭据用测试串，不读环境变量。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from omniread.domain.errors import RagProviderError, RagTimeout
from omniread.infrastructure.providers import (
    GLM_ANSWER_MODEL,
    GLM_BASE_URL,
    ChatModel,
    ChatOptions,
    FakeChatModel,
    GlmChatAdapter,
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
    to_rag_error,
)
from omniread.infrastructure.providers.base import ChatMessage
from omniread.infrastructure.providers.glm import (
    GLM_API_KEY_ENV,
    GLM_REASONING_EFFORT,
    GLM_TEMPERATURE,
    GLM_TOP_P,
)

TEST_KEY = "test-key-not-a-real-credential"

MESSAGES = [
    ChatMessage(role="system", content="只依据材料作答。"),
    ChatMessage(role="user", content="材料……问题……"),
]


def _accepts_chat_model(model: ChatModel) -> None:
    """形参声明即校验：假 provider 与 GLM 适配器都必须满足接口。"""


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _sse_bytes(*chunks: dict[str, Any], done: bool = True) -> bytes:
    lines = [": keep-alive"]
    lines.extend(f"data: {json.dumps(chunk, ensure_ascii=False)}" for chunk in chunks)
    if done:
        lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode("utf-8")


def _delta(content: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = dict(extra)
    if content is not None:
        payload["content"] = content
    return {"choices": [{"delta": payload}]}


def _completion(content: str = "回答", **message_extra: Any) -> httpx.Response:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    message.update(message_extra)
    return httpx.Response(
        200,
        json={"model": GLM_ANSWER_MODEL, "choices": [{"message": message}]},
    )


def test_chat_models_satisfy_the_interface() -> None:
    _accepts_chat_model(FakeChatModel())
    _accepts_chat_model(GlmChatAdapter(api_key=TEST_KEY))


def test_glm_adapter_fails_fast_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GLM_API_KEY_ENV, raising=False)

    with pytest.raises(ProviderConfigError):
        GlmChatAdapter()


async def test_glm_complete_sends_official_sampling_defaults() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured.update(json.loads(request.content))
        return _completion("回答 [C17]")

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        response = await adapter.complete(MESSAGES)

    assert response.text == "回答 [C17]"
    assert response.model == GLM_ANSWER_MODEL
    assert captured["url"] == f"{GLM_BASE_URL}/chat/completions"
    assert captured["auth"] == f"Bearer {TEST_KEY}"
    assert captured["model"] == GLM_ANSWER_MODEL
    assert captured["temperature"] == GLM_TEMPERATURE
    assert captured["top_p"] == GLM_TOP_P
    assert captured["reasoning_effort"] == GLM_REASONING_EFFORT
    assert captured["stream"] is False
    assert captured["messages"] == [
        {"role": "system", "content": "只依据材料作答。"},
        {"role": "user", "content": "材料……问题……"},
    ]
    assert "max_tokens" not in captured


async def test_glm_complete_separates_reasoning_from_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _completion("只交用户正文", reasoning_content="模型推理过程")

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        response = await adapter.complete(MESSAGES)

    assert response.text == "只交用户正文"
    assert response.reasoning == "模型推理过程"


async def test_glm_complete_options_override_defaults() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _completion()

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        await adapter.complete(
            MESSAGES, ChatOptions(temperature=0.2, top_p=0.5, max_tokens=128)
        )

    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.5
    assert captured["max_tokens"] == 128


async def test_glm_complete_rejects_missing_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant"}}]})

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderResponseError):
            await adapter.complete(MESSAGES)


async def test_glm_complete_rejects_malformed_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderResponseError):
            await adapter.complete(MESSAGES)


async def test_glm_complete_http_error_maps_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderError) as info:
            await adapter.complete(MESSAGES)

    error = info.value
    assert error.status_code == 500
    assert TEST_KEY not in str(error)
    rag_error = to_rag_error(error)
    assert isinstance(rag_error, RagProviderError)
    assert rag_error.http_status == 502


async def test_glm_complete_timeout_maps_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderTimeoutError) as info:
            await adapter.complete(MESSAGES)

    rag_error = to_rag_error(info.value)
    assert isinstance(rag_error, RagTimeout)
    assert rag_error.http_status == 504


async def test_glm_stream_yields_content_deltas_and_drops_reasoning() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            content=_sse_bytes(
                _delta(role="assistant"),
                _delta(reasoning_content="这一段推理不给用户"),
                _delta("第一"),
                _delta("第二"),
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"total_tokens": 10}},
            ),
        )

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        chunks = [chunk.text async for chunk in adapter.stream(MESSAGES)]

    assert chunks == ["第一", "第二"]
    assert "".join(chunks) == "第一第二"
    assert captured["stream"] is True
    assert captured["reasoning_effort"] == GLM_REASONING_EFFORT


async def test_glm_stream_emits_before_the_stream_ends() -> None:
    """先 yield 再解析后续分片：畸形分片要能在首块已产出之后才报错。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"\xe9\xa6\x96"}}]}\n\n'
            b"data: not-json\n\n"
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body)

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        stream = adapter.stream(MESSAGES)
        first = await anext(stream)
        assert first.text == "首"
        with pytest.raises(ProviderResponseError):
            await anext(stream)


async def test_glm_stream_requires_the_done_frame() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse_bytes(_delta("没有终止帧"), done=False))

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderResponseError):
            [chunk async for chunk in adapter.stream(MESSAGES)]


async def test_glm_stream_http_error_maps_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderError) as info:
            [chunk async for chunk in adapter.stream(MESSAGES)]

    assert info.value.status_code == 429


async def test_glm_stream_timeout_maps_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    async with _client(handler) as client:
        adapter = GlmChatAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderTimeoutError):
            [chunk async for chunk in adapter.stream(MESSAGES)]


async def test_fake_chat_is_deterministic_and_streams_fixed_slices() -> None:
    first = FakeChatModel(answer="甲乙丙丁戊己庚", chunk_size=3)
    second = FakeChatModel(answer="甲乙丙丁戊己庚", chunk_size=3)

    assert await first.complete(MESSAGES) == await second.complete(MESSAGES)
    early = [chunk.text async for chunk in first.stream(MESSAGES)]
    late = [chunk.text async for chunk in second.stream(MESSAGES)]

    assert early == late == ["甲乙丙", "丁戊己", "庚"]


async def test_fake_chat_rejects_non_positive_chunk_size() -> None:
    with pytest.raises(ValueError):
        FakeChatModel(chunk_size=0)


async def test_fake_chat_records_the_messages_it_received() -> None:
    model = FakeChatModel(answer="好的")

    await model.complete(MESSAGES)
    [chunk async for chunk in model.stream(MESSAGES)]

    assert model.calls == [tuple(MESSAGES), tuple(MESSAGES)]
    assert model.model == "fake-chat"

"""provider 选择：默认真实适配器，显式 fake 才装配假 provider。

关键不变量：fake 是显式开关，不是缺凭据时的降级——真实适配器缺 key 只会失败并被上层
翻译成「未接线」，不会被悄悄替换成假 provider。
"""

from __future__ import annotations

import pytest

from omniread.api.app import (
    build_chat_model,
    build_embedding_model,
    build_query_runner,
    build_rerank_model,
)
from omniread.config import Settings
from omniread.infrastructure.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderTimeoutError,
)
from omniread.infrastructure.providers.fake import (
    FakeChatModel,
    FakeEmbeddingModel,
    FakeRerankModel,
    FaultyChatModel,
)


@pytest.fixture(autouse=True)
def _no_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # 默认路径的真实适配器必须能在没有 key 的机器上断言「构造即失败」。
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)


def test_default_answer_provider_is_glm_without_fallback() -> None:
    with pytest.raises(ProviderConfigError):
        build_chat_model(Settings())


def test_default_retrieval_providers_are_dashscope_without_fallback() -> None:
    with pytest.raises(ProviderConfigError):
        build_embedding_model(Settings())
    with pytest.raises(ProviderConfigError):
        build_rerank_model(Settings())


def test_fake_providers_need_no_key() -> None:
    chat = build_chat_model(Settings(answer_provider="fake"))

    assert isinstance(chat, FakeChatModel)
    assert chat.model == "fake-chat"
    embedder = build_embedding_model(Settings(retrieval_provider="fake"))
    reranker = build_rerank_model(Settings(retrieval_provider="fake"))
    assert isinstance(embedder, FakeEmbeddingModel)
    assert isinstance(reranker, FakeRerankModel)


def test_fake_answer_fault_uses_faulty_model_only_when_asked() -> None:
    normal = build_chat_model(Settings(answer_provider="fake"))
    provider_error = build_chat_model(
        Settings(answer_provider="fake", fake_answer_fault="provider_error")
    )
    timeout = build_chat_model(Settings(answer_provider="fake", fake_answer_fault="timeout"))

    assert isinstance(normal, FakeChatModel)
    assert not isinstance(normal, FaultyChatModel)
    assert isinstance(provider_error, FaultyChatModel)
    assert isinstance(timeout, FaultyChatModel)


@pytest.mark.asyncio
async def test_faulty_chat_model_raises_provider_errors() -> None:
    failing = build_chat_model(Settings(answer_provider="fake", fake_answer_fault="provider_error"))
    timing_out = build_chat_model(Settings(answer_provider="fake", fake_answer_fault="timeout"))

    with pytest.raises(ProviderError) as failure:
        async for _ in failing.stream(()):
            pass
    assert not isinstance(failure.value, ProviderTimeoutError)

    with pytest.raises(ProviderTimeoutError):
        async for _ in timing_out.stream(()):
            pass


def test_answering_chain_is_not_wired_without_retrieval_even_for_fake() -> None:
    assert build_query_runner(None, Settings()) is None
    assert build_query_runner(None, Settings(answer_provider="fake")) is None

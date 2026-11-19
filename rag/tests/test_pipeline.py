import logging
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.config.settings import settings
from app.db.models import Chunk
from app.rag.channels import Channel
from app.rag.generator import Generation
from app.rag.pipeline import ModelGenerationError, RagPipeline
from app.rag.realm import InvalidRealmError
from app.schemas import AskRequest


class FakeEmbedder:
    def embed_query(self, text: str) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=np.float32)


class EmptyVectorStore:
    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class SingleChunkStore:
    def __init__(self) -> None:
        self.chunk = Chunk(
            id=1,
            book_id=1,
            chapter_id="book:1:chapter:1",
            chapter_index=1,
            title="第一章",
            text="证据",
            vector=np.zeros(2, dtype=np.float32),
        )

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return [SimpleNamespace(chunk=self.chunk)]


class NoReranker:
    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[int] | None:
        return None


class FakeRewriter:
    async def rewrite(self, question: str, history: list[Any]) -> str:
        return question


class FailIfCalledGenerator:
    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("generator must not be called without candidates")


class RecordingGenerator:
    def __init__(self, fail_on: Any | None = None) -> None:
        self.calls: list[Any] = []
        self._fail_on = fail_on or (lambda target: False)

    async def generate(
        self, question: str, chunks: list[Chunk], target: Any
    ) -> Generation:
        self.calls.append(target)
        if self._fail_on(target):
            raise RuntimeError(f"upstream failed with {target.api_key}")
        return Generation(
            answer="答案。[[chunk:1]]",
            cited_ids=[1],
            prompt_tokens=12,
            completion_tokens=7,
        )


def make_pipeline(
    generator: Any,
    channels: list[Channel] | None = None,
    *,
    empty: bool = False,
) -> RagPipeline:
    return RagPipeline(
        embedder=FakeEmbedder(),
        generator=generator,
        reranker=NoReranker(),
        rewriter=FakeRewriter(),
        vector_store=EmptyVectorStore() if empty else SingleChunkStore(),
        channels=channels,
    )


@pytest.mark.asyncio
async def test_no_candidates_refuses_without_calling_generator() -> None:
    pipeline = make_pipeline(FailIfCalledGenerator(), channels=[], empty=True)
    response = await pipeline.ask(
        AskRequest(book_id=1, question="问题", level="full", progress=None)
    )

    assert response.answer == "根据已读内容无法回答。"
    assert response.citations == []
    assert response.usage.prompt_tokens == 0
    assert response.usage.completion_tokens == 0


@pytest.mark.asyncio
async def test_invalid_past_progress_fails_before_retrieval() -> None:
    pipeline = make_pipeline(FailIfCalledGenerator(), channels=[])

    with pytest.raises(InvalidRealmError):
        await pipeline.ask(
            AskRequest(book_id=1, question="问题", level="past", progress=0)
        )


@pytest.mark.asyncio
async def test_byok_passes_request_key_and_reports_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    generator = RecordingGenerator()
    pipeline = make_pipeline(generator, channels=[])

    with caplog.at_level(logging.WARNING):
        response = await pipeline.ask(
            AskRequest(
                book_id=1,
                question="问题",
                level="full",
                mode="byok",
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-user-key",
            )
        )

    assert len(generator.calls) == 1
    target = generator.calls[0]
    assert target.provider == "openai"
    assert target.model == "gpt-4o-mini"
    assert target.api_key == "sk-user-key"
    assert response.usage.mode == "byok"
    assert response.usage.provider == "openai"
    assert response.usage.model == "gpt-4o-mini"
    assert response.usage.prompt_tokens == 12
    assert response.usage.completion_tokens == 7
    assert "sk-user-key" not in caplog.text


@pytest.mark.asyncio
async def test_platform_uses_bailian_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "bailian_api_key", "sk-platform")
    generator = RecordingGenerator()
    pipeline = make_pipeline(generator, channels=[])

    response = await pipeline.ask(
        AskRequest(
            book_id=1,
            question="问题",
            level="full",
            mode="platform",
            model="qwen3.7-plus",
        )
    )

    target = generator.calls[0]
    assert target.provider == "bailian"
    assert target.api_key == "sk-platform"
    assert response.usage.mode == "platform"
    assert response.usage.provider == "bailian"


@pytest.mark.asyncio
async def test_auto_tries_channels_in_priority_order(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "bailian_api_key", "")
    channels = [
        Channel("deepseek", "deepseek-chat", "sk-channel-a", priority=1),
        Channel("openai", "gpt-4o-mini", "sk-channel-b", priority=2),
    ]
    generator = RecordingGenerator(
        fail_on=lambda target: target.provider == "deepseek"
    )
    pipeline = make_pipeline(generator, channels=channels)

    with caplog.at_level(logging.WARNING):
        response = await pipeline.ask(
            AskRequest(book_id=1, question="问题", level="full", mode="auto")
        )

    assert [target.provider for target in generator.calls] == [
        "deepseek",
        "openai",
    ]
    assert response.usage.provider == "openai"
    assert response.usage.model == "gpt-4o-mini"
    assert "sk-channel-a" not in caplog.text
    assert "sk-channel-b" not in caplog.text


@pytest.mark.asyncio
async def test_auto_falls_back_to_platform_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "bailian_api_key", "sk-platform")
    monkeypatch.setattr(settings, "chat_model", "qwen3.7-plus")
    channels = [Channel("deepseek", "deepseek-chat", "sk-channel-a", priority=1)]
    generator = RecordingGenerator(
        fail_on=lambda target: target.provider == "deepseek"
    )
    pipeline = make_pipeline(generator, channels=channels)

    with caplog.at_level(logging.WARNING):
        response = await pipeline.ask(
            AskRequest(book_id=1, question="问题", level="full", mode="auto")
        )

    assert generator.calls[-1].fallback is True
    assert response.usage.provider == "bailian"
    assert response.usage.model == "qwen3.7-plus"
    assert "falling back to platform bailian key" in caplog.text
    assert "sk-channel-a" not in caplog.text
    assert "sk-platform" not in caplog.text


@pytest.mark.asyncio
async def test_auto_all_targets_fail_with_safe_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "bailian_api_key", "sk-platform")
    channels = [Channel("deepseek", "deepseek-chat", "sk-channel-a", priority=1)]
    generator = RecordingGenerator(fail_on=lambda target: True)
    pipeline = make_pipeline(generator, channels=channels)

    with caplog.at_level(logging.WARNING), pytest.raises(ModelGenerationError) as info:
        await pipeline.ask(
            AskRequest(book_id=1, question="问题", level="full", mode="auto")
        )

    assert "sk-channel-a" not in caplog.text
    assert "sk-platform" not in caplog.text
    assert "sk-channel-a" not in str(info.value)
    assert "sk-platform" not in str(info.value)
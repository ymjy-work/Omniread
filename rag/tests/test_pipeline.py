import pytest

from app.rag.pipeline import RagPipeline
from app.rag.realm import InvalidRealmError
from app.schemas import AskRequest


class FakeEmbedder:
    def embed_query(self, text: str):
        import numpy as np

        return np.asarray([1.0, 0.0], dtype=np.float32)


class EmptyVectorStore:
    def search(self, *args, **kwargs):
        return []


class FailIfCalledGenerator:
    async def generate(self, *args, **kwargs):
        raise AssertionError("generator must not be called without candidates")


@pytest.mark.asyncio
async def test_no_candidates_refuses_without_calling_generator() -> None:
    pipeline = RagPipeline(
        embedder=FakeEmbedder(),
        generator=FailIfCalledGenerator(),
        vector_store=EmptyVectorStore(),
    )
    response = await pipeline.ask(
        AskRequest(book_id=1, question="问题", level="full", progress=None)
    )

    assert response.answer == "根据已读内容无法回答。"
    assert response.citations == []


@pytest.mark.asyncio
async def test_invalid_past_progress_fails_before_retrieval() -> None:
    pipeline = RagPipeline(
        embedder=FakeEmbedder(),
        generator=FailIfCalledGenerator(),
        vector_store=EmptyVectorStore(),
    )

    with pytest.raises(InvalidRealmError):
        await pipeline.ask(
            AskRequest(book_id=1, question="问题", level="past", progress=0)
        )

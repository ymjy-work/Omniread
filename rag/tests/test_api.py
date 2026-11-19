from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.rag.pipeline import ModelGenerationError
from app.rag.realm import chapter_range
from app.schemas import (
    AskRequest,
    AskResponse,
    AskUsage,
    Citation,
    IndexRequest,
    IndexResponse,
)


class MockPipeline:
    async def index(self, request: IndexRequest) -> IndexResponse:
        return IndexResponse(indexed_chunks=len(request.chapters))

    async def ask(self, request: AskRequest) -> AskResponse:
        chapter_range(request.level, request.progress)
        return AskResponse(
            answer="模拟答案。",
            citations=[
                Citation(
                    chapter_id="book:1:chapter:1",
                    chapter_index=1,
                    title="第一章",
                    quote="模拟引用",
                )
            ],
            usage=AskUsage(
                mode=request.mode,
                provider="bailian",
                model="qwen3.7-plus",
                prompt_tokens=1,
                completion_tokens=2,
            ),
        )


class FailingPipeline(MockPipeline):
    async def ask(self, request: AskRequest) -> AskResponse:
        raise ModelGenerationError("generation failed: openai/gpt-4o-mini")


def make_client(pipeline: Any | None = None) -> TestClient:
    return TestClient(create_app(pipeline or MockPipeline()))


def test_health() -> None:
    with make_client() as client:
        response = client.get("/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_index_returns_chunk_count() -> None:
    payload: dict[str, Any] = {
        "book_id": 1,
        "chapters": [
            {
                "chapter_id": "book:1:chapter:1",
                "chapter_index": 1,
                "title": "第一章",
                "text": "正文",
            }
        ],
    }
    with make_client() as client:
        response = client.post("/v1/index", json=payload)
    assert response.status_code == 200
    assert response.json() == {"indexed_chunks": 1}


def test_ask_and_invalid_past_progress() -> None:
    with make_client() as client:
        response = client.post(
            "/v1/ask",
            json={
                "book_id": 1,
                "question": "问题",
                "level": "past",
                "progress": 2,
                "history": [],
                "top_k": 8,
            },
        )
        invalid = client.post(
            "/v1/ask",
            json={
                "book_id": 1,
                "question": "问题",
                "level": "past",
                "progress": 194,
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "模拟答案。"
    assert response.json()["citations"][0]["chapter_id"] == "book:1:chapter:1"
    assert response.json()["usage"]["mode"] == "auto"
    assert invalid.status_code == 400


def test_ask_byok_returns_usage() -> None:
    with make_client() as client:
        response = client.post(
            "/v1/ask",
            json={
                "book_id": 1,
                "question": "问题",
                "level": "full",
                "mode": "byok",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "sk-user-key",
            },
        )

    assert response.status_code == 200
    assert response.json()["usage"]["mode"] == "byok"


def test_auto_mode_rejects_api_key_without_echoing_it() -> None:
    with make_client() as client:
        response = client.post(
            "/v1/ask",
            json={
                "book_id": 1,
                "question": "问题",
                "level": "full",
                "mode": "auto",
                "api_key": "sk-secret",
            },
        )

    assert response.status_code == 422
    assert "sk-secret" not in response.text
    assert "api_key" in response.text


def test_generation_error_maps_to_502() -> None:
    with make_client(FailingPipeline()) as client:
        response = client.post(
            "/v1/ask",
            json={"book_id": 1, "question": "问题", "level": "full"},
        )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "generation failed: openai/gpt-4o-mini"
    }
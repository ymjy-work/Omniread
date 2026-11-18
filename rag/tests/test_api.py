from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.rag.realm import chapter_range
from app.schemas import AskRequest, AskResponse, Citation, IndexRequest, IndexResponse


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
        )


def make_client() -> TestClient:
    return TestClient(create_app(MockPipeline()))


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
    assert invalid.status_code == 400

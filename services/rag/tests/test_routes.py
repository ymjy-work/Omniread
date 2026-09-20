"""路由与响应形状：8 条路径都在，形状与契约一致。

默认 fixture 注入空目录与未接线 runner，因此 catalog 端点返回空结构、rag 端点以
RAG_UNAVAILABLE 收尾；SSE 帧编码本身是真实的（注入假事件流的 `streaming_client`
走一遍完整序列）。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from helpers import REQUEST_ID, fake_event_sequence, parse_sse_frames

QUERY_BODY = {
    "book_id": 1,
    "question": "政近为什么离开周防家？",
    "level": "past",
    "progress": 45,
    "options": {"rewrite": False, "neighbor_expand": True},
}

CONTRACT_PATHS = [
    "/internal/v1/health",
    "/internal/v1/books",
    "/internal/v1/books/1/chapters",
    "/internal/v1/books/1/chapters/17",
    "/internal/v1/books/1/images/01_第1卷/007.jpg",
    "/internal/v1/rag/query",
    "/internal/v1/rag/query-stream",
    "/internal/v1/rag/retrieval-only",
]


def test_health_reports_own_service(client: TestClient) -> None:
    response = client.get("/internal/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "omniread-rag"}


def test_books_returns_empty_structure(client: TestClient) -> None:
    response = client.get("/internal/v1/books")

    assert response.status_code == 200
    assert response.json() == {"books": []}


def test_chapters_returns_empty_structure(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/chapters")

    assert response.status_code == 200
    assert response.json() == {"book_id": 1, "chapters": []}


def test_progress_route_is_not_registered(client: TestClient) -> None:
    # 进度由 Java 侧持久化，内部契约没有这条路径（M0-01 §1）。
    assert client.get("/internal/v1/books/1/progress").status_code == 404


@pytest.mark.parametrize("path", CONTRACT_PATHS)
def test_contract_paths_are_routed(client: TestClient, path: str) -> None:
    # 任意已注册路径都不该是 405 / 404「没有这条路由」。
    method = "post" if "/rag/" in path else "get"
    request = getattr(client, method)
    response = request(path, **({"json": QUERY_BODY} if method == "post" else {}))

    assert response.status_code != 405


def test_query_without_pipeline_returns_unavailable_error_body(client: TestClient) -> None:
    response = client.post("/internal/v1/rag/query", json=QUERY_BODY)

    assert response.status_code == 503
    assert set(response.json()) == {"request_id", "code", "message"}
    assert response.json()["code"] == "RAG_UNAVAILABLE"


def test_retrieval_only_without_pipeline_returns_error_body(client: TestClient) -> None:
    response = client.post("/internal/v1/rag/retrieval-only", json=QUERY_BODY)

    assert response.status_code == 503
    assert response.json()["code"] == "RAG_UNAVAILABLE"


def test_query_stream_without_pipeline_emits_error_frame(client: TestClient) -> None:
    response = client.post("/internal/v1/rag/query-stream", json=QUERY_BODY)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    assert [event for event, _ in frames] == ["error"]
    assert json.loads(frames[0][1])["code"] == "RAG_UNAVAILABLE"
    assert "[DONE]" not in response.text


def test_query_stream_encodes_full_fake_sequence(streaming_client: TestClient) -> None:
    response = streaming_client.post(
        "/internal/v1/rag/query-stream",
        json=QUERY_BODY,
        headers={"X-Request-Id": REQUEST_ID},
    )

    assert response.status_code == 200
    frames = parse_sse_frames(response.text)
    expected_events = [event.name.value for event in fake_event_sequence()]
    assert [event for event, _ in frames] == [*expected_events, None]
    assert frames[-1][1] == "[DONE]"

    payloads = [json.loads(data) for _, data in frames[:-1]]
    assert payloads[0]["request_id"] == REQUEST_ID
    assert payloads[0]["progress"] == 45
    answer = "".join(item["text"] for item in payloads if "text" in item)
    assert answer == "政近离开了周防家。\n\n依据 [C17]。"
    assert payloads[-1]["status"] == "answered"


def test_query_folds_fake_sequence_into_json_object(streaming_client: TestClient) -> None:
    response = streaming_client.post(
        "/internal/v1/rag/query", json=QUERY_BODY, headers={"X-Request-Id": REQUEST_ID}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"request_id", "status", "answer", "context_chapters", "usage"}
    assert body["request_id"] == REQUEST_ID
    assert body["status"] == "answered"
    assert body["context_chapters"] == [
        {"chapter_index": 17, "chapter_title": "第3话 主仆逆转的释义似乎因人而异"}
    ]
    assert body["usage"] == {
        "answer_provider": "glm",
        "answer_model": "glm-5.3-flash",
        "latency_ms": 1830,
    }

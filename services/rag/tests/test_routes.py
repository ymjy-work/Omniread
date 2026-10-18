"""路由与响应形状：8 条路径都在，形状与契约一致。

默认 fixture 注入空目录与未接线 runner，因此 catalog 端点返回空结构、rag 端点以
RAG_UNAVAILABLE 收尾；SSE 帧编码本身是真实的（注入假事件流的 `streaming_client`
走一遍完整序列）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import build_client_with_runner
from helpers import REQUEST_ID, FakeQueryRunner, fake_event_sequence, parse_sse_frames
from omniread.domain.events import EventName, RagEvent, rewrite_completed

QUERY_BODY = {
    "book_id": 1,
    "question": "政近为什么离开周防家？",
    "level": "past",
    "progress": 45,
    "options": {"rewrite": False, "neighbor_expand": True},
}

SUMMARIZE_BODY = {
    "previous_summary": None,
    "messages": [
        {"role": "user", "content": "政近为什么离开周防家？"},
        {"role": "assistant", "content": "因为家里出了事 [C17]。"},
    ],
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
    "/internal/v1/summarize",
]

# 路径 → 方法显式写死，**不按子串猜**：`/internal/v1/summarize` 不含 `/rag/`，
# 用「含 /rag/ 就当 POST」那条规则会把它当 GET 发出去、吃一个 405——
# 而那正是这条用例要区分的东西（405 说明路由没挂上，不是方法用错了）。
POST_PATHS = {
    "/internal/v1/rag/query",
    "/internal/v1/rag/query-stream",
    "/internal/v1/rag/retrieval-only",
    "/internal/v1/summarize",
}


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
    # 进度由 Java 侧持久化，内部契约没有这条路径。
    assert client.get("/internal/v1/books/1/progress").status_code == 404


@pytest.mark.parametrize("path", CONTRACT_PATHS)
def test_contract_paths_are_routed(client: TestClient, path: str) -> None:
    # 任意已注册路径都不该是 405 / 404「没有这条路由」。
    method = "post" if path in POST_PATHS else "get"
    request = getattr(client, method)
    body = SUMMARIZE_BODY if path == "/internal/v1/summarize" else QUERY_BODY
    response = request(path, **({"json": body} if method == "post" else {}))

    assert response.status_code != 405


def test_summarize_without_pipeline_returns_unavailable_error_body(client: TestClient) -> None:
    """摘要是**未接线 503**，不是「返回一份空摘要」。

    契约的响应两个字段都 required，没有「这次不摘要」的取值——静默回一份空摘要
    会写进会话、让后面每一轮都少一段上下文，而那是查不出来的。
    """
    response = client.post("/internal/v1/summarize", json=SUMMARIZE_BODY)

    assert response.status_code == 503
    assert response.json()["code"] == "RAG_UNAVAILABLE"


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


REWRITTEN = "周防家的女儿后来怎么样了？"


def _sequence_with_rewrite(effective: str) -> list[RagEvent]:
    """在完整序列里插一帧改写结果。

    位置按契约：`realm_resolved` 之后、`retrieval_completed` 之前。
    """
    events = fake_event_sequence()
    at = next(
        index
        for index, event in enumerate(events)
        if event.name is EventName.RETRIEVAL_COMPLETED
    )
    events.insert(
        at,
        rewrite_completed(status="rewritten", original="那她后来呢？", effective=effective),
    )
    return events


def test_json_fold_takes_rewritten_query_from_the_frame(image_root: Path) -> None:
    """`rewritten_query` 只能从 `rewrite_completed` 那一帧拿。

    `query_done` 的负载被契约写死成 status / context_chapters / usage，没有它的位置——
    少了这条捕获，字段会永远为 null，而那是**合法值**，所以不会有任何测试变红。
    """
    client = build_client_with_runner(
        image_root, FakeQueryRunner(_sequence_with_rewrite(REWRITTEN))
    )
    response = client.post("/internal/v1/rag/query", json=QUERY_BODY)

    assert response.status_code == 200
    assert response.json()["rewritten_query"] == REWRITTEN


def test_sse_carries_the_rewrite_frame(image_root: Path) -> None:
    client = build_client_with_runner(
        image_root, FakeQueryRunner(_sequence_with_rewrite(REWRITTEN))
    )
    response = client.post("/internal/v1/rag/query-stream", json=QUERY_BODY)

    frames = parse_sse_frames(response.text)
    names = [name for name, _ in frames]
    assert "rewrite_completed" in names
    # 顺序：改写结果在检索之前（改完才用它去检索）。
    assert names.index("rewrite_completed") < names.index("retrieval_completed")
    # 载荷与契约的 RewriteOutcome 逐字段一致：effective 无论哪种状态都有值。
    assert json.loads(dict(frames)["rewrite_completed"]) == {
        "status": "rewritten",
        "original": "那她后来呢？",
        "effective": REWRITTEN,
    }


def test_query_folds_fake_sequence_into_json_object(streaming_client: TestClient) -> None:
    response = streaming_client.post(
        "/internal/v1/rag/query", json=QUERY_BODY, headers={"X-Request-Id": REQUEST_ID}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "request_id",
        "status",
        "answer",
        "context_chapters",
        "usage",
        "rewritten_query",
    }
    assert body["request_id"] == REQUEST_ID
    assert body["status"] == "answered"
    # 这个请求没有历史，改写落 skipped、不发帧，所以这里是 null——**字段在、值是空**
    # 才是契约要的形状（「没改写」与「字段没下发」是不同的事）。
    assert body["rewritten_query"] is None
    assert body["context_chapters"] == [
        {"chapter_index": 17, "chapter_title": "第3话 主仆逆转的释义似乎因人而异"}
    ]
    assert body["usage"] == {
        "answer_provider": "glm",
        "answer_model": "glm-5.3-flash",
        "latency_ms": 1830,
    }

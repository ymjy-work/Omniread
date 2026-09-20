"""测试共用的假事件序列与 runner。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from omniread.domain.events import (
    AnswerStatus,
    RagEvent,
    answer_delta,
    citation_ready,
    context_assembled,
    generation_started,
    query_done,
    query_started,
    realm_resolved,
    rerank_completed,
    retrieval_completed,
)
from omniread.domain.models import QueryRequest

REQUEST_ID = "req_0123456789abcdef0123456789abcdef"

CONTEXT_CHAPTERS = [
    {"chapter_index": 17, "chapter_title": "第3话 主仆逆转的释义似乎因人而异"}
]


def fake_event_sequence() -> list[RagEvent]:
    """一段完整的成功事件序列，字段取自 M0-02 §8.5 的负载表。"""
    return [
        query_started(request_id=REQUEST_ID, book_id=1, level="past", progress=45),
        realm_resolved(lo=1, hi=45),
        retrieval_completed(
            dense_count=60,
            bm25_count=60,
            fused_count=12,
            fused_top=[{"chunk_key": "book:1:chapter:17#c3"}],
        ),
        rerank_completed(
            input_count=12,
            output_count=12,
            ranked=[{"chunk_key": "book:1:chapter:17#c3", "score": 0.91}],
        ),
        context_assembled(
            chunks=[
                {"chunk_key": "book:1:chapter:17#c3", "chapter_index": 17, "source": "hit"}
            ],
            token_estimate=520,
            dropped=[],
        ),
        generation_started(
            answer_provider="glm",
            answer_model="glm-5.3-flash",
            prompt_version="deadbeef",
        ),
        answer_delta(text="政近离开了周防家。"),
        answer_delta(text="\n\n依据 [C17]。"),
        citation_ready(context_chapters=CONTEXT_CHAPTERS),
        query_done(
            status=AnswerStatus.ANSWERED,
            context_chapters=CONTEXT_CHAPTERS,
            usage={
                "answer_provider": "glm",
                "answer_model": "glm-5.3-flash",
                "latency_ms": 1830,
            },
        ),
    ]


class FakeQueryRunner:
    """按给定事件序列作答的 runner。"""

    def __init__(self, events: list[RagEvent] | None = None) -> None:
        self._events = fake_event_sequence() if events is None else events

    async def run(self, request: QueryRequest, request_id: str) -> AsyncIterator[RagEvent]:
        for event in self._events:
            yield event


class FailingQueryRunner:
    """产出若干事件后抛异常，模拟生成中途的 provider 故障。"""

    def __init__(self, error: Exception, events: list[RagEvent] | None = None) -> None:
        self._error = error
        self._events = events or []

    async def run(self, request: QueryRequest, request_id: str) -> AsyncIterator[RagEvent]:
        for event in self._events:
            yield event
        raise self._error


def parse_sse_frames(raw: str) -> list[tuple[str | None, str]]:
    """把 SSE 全文拆成 (event, data) 列表；`[DONE]` 帧没有 event 行。"""
    frames: list[tuple[str | None, str]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event: str | None = None
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        frames.append((event, data))
    return frames

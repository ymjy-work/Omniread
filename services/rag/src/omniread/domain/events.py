"""内部事件流：事件名、顺序、负载的唯一来源。

RAG core 只产生本模块定义的事件，`api.adapters` 里的两个适配器只负责把它们编码成
JSON 对象或 SSE 帧，不含业务逻辑。字段口径见
`docs/m0/M0-02-数据结构设计.md` §8.5，事件名集合由契约 `EventStream.event` 冻结。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventName(StrEnum):
    QUERY_STARTED = "query_started"
    REALM_RESOLVED = "realm_resolved"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    RERANK_COMPLETED = "rerank_completed"
    CONTEXT_ASSEMBLED = "context_assembled"
    GENERATION_STARTED = "generation_started"
    ANSWER_DELTA = "answer_delta"
    CITATION_READY = "citation_ready"
    QUERY_DONE = "query_done"
    QUERY_ERROR = "query_error"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


# 一次成功问答的顺序：检索四步毫秒级完成、无可下发增量，生成逐段下发。
# query_done 与 query_error 互斥且必须最后。
EVENT_ORDER: tuple[EventName, ...] = (
    EventName.QUERY_STARTED,
    EventName.REALM_RESOLVED,
    EventName.RETRIEVAL_COMPLETED,
    EventName.RERANK_COMPLETED,
    EventName.CONTEXT_ASSEMBLED,
    EventName.GENERATION_STARTED,
    EventName.ANSWER_DELTA,
    EventName.CITATION_READY,
    EventName.QUERY_DONE,
)


@dataclass(frozen=True, slots=True)
class RagEvent:
    name: EventName
    payload: dict[str, Any] = field(default_factory=dict)


def query_started(
    *, request_id: str, book_id: int, level: str, progress: int | None
) -> RagEvent:
    return RagEvent(
        EventName.QUERY_STARTED,
        {"request_id": request_id, "book_id": book_id, "level": level, "progress": progress},
    )


def realm_resolved(*, lo: int, hi: int) -> RagEvent:
    return RagEvent(EventName.REALM_RESOLVED, {"lo": lo, "hi": hi})


def retrieval_completed(
    *,
    dense_count: int,
    bm25_count: int,
    fused_count: int,
    fused_top: list[dict[str, Any]],
) -> RagEvent:
    return RagEvent(
        EventName.RETRIEVAL_COMPLETED,
        {
            "dense_count": dense_count,
            "bm25_count": bm25_count,
            "fused_count": fused_count,
            "fused_top": fused_top,
        },
    )


def rerank_completed(
    *, input_count: int, output_count: int, ranked: list[dict[str, Any]]
) -> RagEvent:
    return RagEvent(
        EventName.RERANK_COMPLETED,
        {"input_count": input_count, "output_count": output_count, "ranked": ranked},
    )


def context_assembled(
    *,
    chunks: list[dict[str, Any]],
    token_estimate: int,
    dropped: list[dict[str, Any]],
) -> RagEvent:
    return RagEvent(
        EventName.CONTEXT_ASSEMBLED,
        {"chunks": chunks, "token_estimate": token_estimate, "dropped": dropped},
    )


def generation_started(
    *, answer_provider: str, answer_model: str, prompt_version: str
) -> RagEvent:
    return RagEvent(
        EventName.GENERATION_STARTED,
        {
            "answer_provider": answer_provider,
            "answer_model": answer_model,
            "prompt_version": prompt_version,
        },
    )


def answer_delta(*, text: str) -> RagEvent:
    return RagEvent(EventName.ANSWER_DELTA, {"text": text})


def citation_ready(*, context_chapters: list[dict[str, Any]]) -> RagEvent:
    return RagEvent(EventName.CITATION_READY, {"context_chapters": context_chapters})


def query_done(
    *,
    status: AnswerStatus,
    context_chapters: list[dict[str, Any]],
    usage: dict[str, Any],
) -> RagEvent:
    return RagEvent(
        EventName.QUERY_DONE,
        {"status": status.value, "context_chapters": context_chapters, "usage": usage},
    )


def query_error(*, request_id: str, code: str, message: str) -> RagEvent:
    return RagEvent(
        EventName.QUERY_ERROR, {"request_id": request_id, "code": code, "message": message}
    )

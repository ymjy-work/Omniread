"""问答链：事件流不变量、JSON / SSE 同一份行为、拒答与 provider 故障。

全部用假 provider 与内存替身，不发真实调用、不连库。同一个 `AnsweringRunner` 产出的
事件流分别喂给两个适配器，验证「行为只定义一次」——两边表达的是同一件事。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import build_client_with_runner
from helpers import REQUEST_ID, parse_sse_frames
from omniread.api.adapters import JsonResponseAdapter, SseResponseAdapter
from omniread.application.query_service import REFUSAL_ANSWER, AnsweringRunner
from omniread.domain.errors import RagProviderError, RagTimeout, RagUnavailable
from omniread.domain.events import AnswerStatus, EventName, RagEvent
from omniread.domain.models import ContextChunk, QueryRequest, RealmLevel
from omniread.infrastructure.providers.base import ChatChunk, ChatMessage, ChatOptions
from omniread.infrastructure.providers.errors import (
    ProviderError,
    ProviderTimeoutError,
)
from omniread.infrastructure.providers.fake import FakeChatModel
from omniread.pipelines.answering import REFUSAL_MARKER
from omniread.pipelines.assembly import AssembledChunk
from omniread.pipelines.retrieval.query import RealmBounds
from omniread.pipelines.retrieval.types import RetrievalOutcome, StageHit

REALM = RealmBounds(lo=1, hi=193)


def _key(chapter: int, index: int = 0) -> str:
    return f"book:1:chapter:{chapter}#c{index}"


def _hit(key: str, chapter: int, rank: int) -> StageHit:
    return StageHit(chunk_key=key, chapter_index=chapter, score=0.9 - rank / 100, rank=rank)


def _assembled(
    key: str, chapter: int, chunk_index: int = 0, source: str = "hit", rank: int = 1
) -> AssembledChunk:
    return AssembledChunk(
        chunk_key=key,
        chapter_index=chapter,
        chunk_index=chunk_index,
        source=source,  # type: ignore[arg-type]
        from_hit_chunk_key=key,
        token_count=100,
        rank=rank,
    )


def _context(chapter: int, key: str) -> ContextChunk:
    return ContextChunk(
        chunk_key=key,
        chapter_index=chapter,
        chapter_title=f"第{chapter}章 标题",
        text=f"第{chapter}章的正文内容。",
    )


def _outcome(assembled: Sequence[AssembledChunk]) -> RetrievalOutcome:
    fused = tuple(
        _hit(item.chunk_key, item.chapter_index, item.rank) for item in assembled
    )
    return RetrievalOutcome(
        query="政近 离开",
        realm=REALM,
        dense=fused,
        kw=fused,
        fused=fused,
        reranked=fused,
        assembled=tuple(assembled),
        dropped=(),
        token_estimate=sum(item.token_count for item in assembled),
    )


class StubRetrieval:
    def __init__(
        self, outcome: RetrievalOutcome | None = None, error: Exception | None = None
    ) -> None:
        self._outcome = outcome
        self._error = error

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome:
        if self._error is not None:
            raise self._error
        assert self._outcome is not None
        return self._outcome


class StubContext:
    def __init__(self, chunks: Sequence[ContextChunk]) -> None:
        self._by_key = {chunk.chunk_key: chunk for chunk in chunks}

    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
        return [self._by_key[key] for key in chunk_keys if key in self._by_key]


class PartialThenFailingChat:
    """先产出一段正文再抛 provider 超时，模拟生成中途故障。"""

    model = "fake-chat"

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        yield ChatChunk(text="开了个头")
        raise ProviderTimeoutError("provider 超时", provider="fake")


def _runner(
    *,
    outcome: RetrievalOutcome | None = None,
    chunks: Sequence[ContextChunk] = (),
    chat: Any = None,
    retrieval_error: Exception | None = None,
    context: Any = None,
) -> tuple[AnsweringRunner, Any]:
    chat = chat or FakeChatModel(answer="政近是因为家族安排离开的 [C17]。")
    runner = AnsweringRunner(
        retrieval=StubRetrieval(outcome, retrieval_error),
        context=context or StubContext(chunks),
        chat=chat,
        answer_provider="fake",
    )
    return runner, chat


def _request() -> QueryRequest:
    return QueryRequest(book_id=1, question="政近为什么离开周防家？", level=RealmLevel.FULL)


async def _events(runner: AnsweringRunner) -> list[RagEvent]:
    return [event async for event in runner.run(_request(), REQUEST_ID)]


def _answered_case() -> tuple[AnsweringRunner, list[ContextChunk]]:
    assembled = [_assembled(_key(17), 17), _assembled(_key(45), 45)]
    chunks = [_context(17, _key(17)), _context(45, _key(45))]
    runner, _ = _runner(outcome=_outcome(assembled), chunks=chunks)
    return runner, chunks


# ---- 事件顺序不变量 --------------------------------------------------------


async def test_answered_event_order_invariants() -> None:
    runner, _ = _answered_case()

    events = await _events(runner)
    names = [event.name for event in events]

    assert names[0] is EventName.QUERY_STARTED
    assert names[-1] is EventName.QUERY_DONE
    assert EventName.QUERY_ERROR not in names
    assert names.count(EventName.QUERY_DONE) == 1

    generation = names.index(EventName.GENERATION_STARTED)
    deltas = [index for index, name in enumerate(names) if name is EventName.ANSWER_DELTA]
    assert deltas, "作答路径必须有正文增量"
    assert all(index > generation for index in deltas)
    assert names.index(EventName.CITATION_READY) > max(deltas)
    assert names.index(EventName.CONTEXT_ASSEMBLED) < generation


async def test_refusal_event_order_invariants() -> None:
    runner, _ = _runner(outcome=_outcome([]))

    events = await _events(runner)
    names = [event.name for event in events]

    assert names[0] is EventName.QUERY_STARTED
    assert names[-1] is EventName.QUERY_DONE
    assert EventName.QUERY_ERROR not in names
    # 拒答同样走 generation_started → answer_delta，适配器因此不需要拒答分支。
    assert names.index(EventName.GENERATION_STARTED) < names.index(EventName.ANSWER_DELTA)


async def test_middle_events_carry_contract_payloads() -> None:
    runner, _ = _answered_case()

    events = await _events(runner)
    payloads = {event.name: event.payload for event in events}

    assert payloads[EventName.QUERY_STARTED] == {
        "request_id": REQUEST_ID,
        "book_id": 1,
        "level": "full",
        "progress": None,
    }
    assert payloads[EventName.REALM_RESOLVED] == {"lo": 1, "hi": 193}
    assert set(payloads[EventName.RETRIEVAL_COMPLETED]) == {
        "dense_count",
        "bm25_count",
        "fused_count",
        "fused_top",
    }
    assert set(payloads[EventName.RERANK_COMPLETED]) == {
        "input_count",
        "output_count",
        "ranked",
    }
    assembled = payloads[EventName.CONTEXT_ASSEMBLED]
    assert set(assembled) == {"chunks", "token_estimate", "dropped"}
    assert assembled["chunks"] == [
        {"chunk_key": _key(17), "chapter_index": 17, "source": "hit"},
        {"chunk_key": _key(45), "chapter_index": 45, "source": "hit"},
    ]
    assert set(payloads[EventName.GENERATION_STARTED]) == {
        "answer_provider",
        "answer_model",
        "prompt_version",
    }


# ---- 两个适配器表达同一件事 ------------------------------------------------


async def test_json_fold_and_sse_frames_express_the_same_answer() -> None:
    runner, _ = _answered_case()
    events = await _events(runner)

    async def replay() -> AsyncIterator[RagEvent]:
        for event in events:
            yield event

    response = await JsonResponseAdapter.fold(replay(), request_id=REQUEST_ID)
    frames = [frame async for frame in SseResponseAdapter.stream(replay(), request_id=REQUEST_ID)]
    parsed = [parse_sse_frames(frame)[0] for frame in frames]

    assert [name for name, _ in parsed] == [
        *(event.name.value for event in events),
        None,
    ]
    assert parsed[-1][1] == "[DONE]"

    deltas = [event.payload["text"] for event in events if event.name is EventName.ANSWER_DELTA]
    assert response.answer == "".join(deltas)
    assert response.status == AnswerStatus.ANSWERED

    done = json.loads(parsed[-2][1])
    expected_chapters = [chapter.model_dump() for chapter in response.context_chapters]
    assert done["status"] == response.status
    assert done["context_chapters"] == expected_chapters
    assert done["usage"] == response.usage.model_dump()
    assert response.context_chapters[0].chapter_index == 17


# ---- 拒答 ------------------------------------------------------------------


async def test_insufficient_evidence_uses_server_fixed_answer_and_skips_model() -> None:
    runner, chat = _runner(outcome=_outcome([]))

    events = await _events(runner)
    payloads = {event.name: event.payload for event in events}
    deltas = [event.payload["text"] for event in events if event.name is EventName.ANSWER_DELTA]

    assert payloads[EventName.QUERY_DONE]["status"] == "insufficient_evidence"
    assert deltas == [REFUSAL_ANSWER]
    assert payloads[EventName.CITATION_READY]["context_chapters"] == []
    assert payloads[EventName.QUERY_DONE]["context_chapters"] == []
    assert payloads[EventName.RETRIEVAL_COMPLETED]["fused_count"] == 0
    # 固定话术来自服务端常量，模型在拒答路径上根本不被调用。
    assert chat.calls == []


async def test_refusal_in_json_route_is_200_with_fixed_answer(image_root) -> None:
    runner, _ = _runner(outcome=_outcome([]))
    client: TestClient = build_client_with_runner(image_root, runner)

    response = client.post(
        "/internal/v1/rag/query",
        json={"book_id": 1, "question": "问题", "level": "full"},
        headers={"X-Request-Id": REQUEST_ID},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert body["answer"] == REFUSAL_ANSWER
    assert body["context_chapters"] == []


def _model_level_refusal_case() -> AnsweringRunner:
    """模型级拒答（M0-02 §8.3）：有上下文，但模型按模板要求以标记开头作答。

    `chunk_size=5` 让标记 `[INSUFFICIENT]` 必然被切成多个分片——跨块的判定是这条
    路径最容易写错的地方（只对单块判就会漏）。
    """
    assembled = [_assembled(_key(17), 17)]
    runner, _ = _runner(
        outcome=_outcome(assembled),
        chunks=[_context(17, _key(17))],
        chat=FakeChatModel(answer=REFUSAL_MARKER, chunk_size=5),
    )
    return runner


def test_model_level_refusal_replaces_the_answer_and_keeps_context_chapters(
    image_root,
) -> None:
    """模型级拒答经两个适配器表达同一件事：固定话术 + **非空** `context_chapters`。

    §8.3 正是用 `context_chapters` 空不空区分「检索为空」与「模型答不了」，
    所以这条路径不能把章号清掉。
    """
    expected = [{"chapter_index": 17, "chapter_title": "第17章 标题"}]
    client: TestClient = build_client_with_runner(image_root, _model_level_refusal_case())

    body = client.post(
        "/internal/v1/rag/query",
        json={"book_id": 1, "question": "问题", "level": "full"},
        headers={"X-Request-Id": REQUEST_ID},
    ).json()
    stream = client.post(
        "/internal/v1/rag/query-stream",
        json={"book_id": 1, "question": "问题", "level": "full"},
        headers={"X-Request-Id": REQUEST_ID},
    )
    frames = parse_sse_frames(stream.text)

    assert body["status"] == "insufficient_evidence"
    assert body["answer"] == REFUSAL_ANSWER
    assert body["context_chapters"] == expected
    citation = json.loads(next(data for event, data in frames if event == "citation_ready"))
    done = json.loads(next(data for event, data in frames if event == "query_done"))
    assert citation["context_chapters"] == expected
    assert done["context_chapters"] == expected
    # 标记本身绝不能出现在响应里：它只在服务端内部表示「这条要换成拒答话术」。
    deltas = [json.loads(data)["text"] for event, data in frames if event == "answer_delta"]
    assert "".join(deltas) == REFUSAL_ANSWER


# ---- 模型级拒答标记（M1-2）------------------------------------------------


def _marker_chat(answer: str, *, chunk_size: int = 4) -> AnsweringRunner:
    runner, _ = _runner(
        outcome=_outcome([_assembled(_key(17), 17)]),
        chunks=[_context(17, _key(17))],
        chat=FakeChatModel(answer=answer, chunk_size=chunk_size),
    )
    return runner


async def _answer_text_and_status(runner: AnsweringRunner) -> tuple[str, str]:
    events = await _events(runner)
    done = next(event for event in events if event.name is EventName.QUERY_DONE)
    text = "".join(
        event.payload["text"] for event in events if event.name is EventName.ANSWER_DELTA
    )
    return text, done.payload["status"]


async def test_marker_split_across_chunks_is_detected() -> None:
    # 标记被切成 5 个分片（chunk_size=5）：判定必须能跨块拼接，只看单块会漏。
    assert len(REFUSAL_MARKER) > 5

    text, status = await _answer_text_and_status(_marker_chat(REFUSAL_MARKER, chunk_size=5))

    assert status == "insufficient_evidence"
    assert text == REFUSAL_ANSWER
    assert REFUSAL_MARKER not in text


async def test_marker_after_leading_whitespace_is_still_a_refusal() -> None:
    text, status = await _answer_text_and_status(
        _marker_chat(f"\n\n  {REFUSAL_MARKER}", chunk_size=3)
    )

    assert status == "insufficient_evidence"
    assert text == REFUSAL_ANSWER


async def test_marker_in_the_middle_is_not_a_refusal_and_is_not_removed() -> None:
    # 只认开头，且不改写模型输出（M0-04 §4）：中段的标记与越界引用同一条口径，原样保留。
    answer = f"材料里没有直接说明，[C17] 但这句提到了 {REFUSAL_MARKER} 这个词。"

    text, status = await _answer_text_and_status(_marker_chat(answer, chunk_size=3))

    assert status == "answered"
    assert text == answer


async def test_stream_ending_mid_marker_is_not_a_refusal() -> None:
    # 模型吐了半截标记就断流：不是拒答，压着的文本必须照常吐出去（不能吞字）。
    text, status = await _answer_text_and_status(_marker_chat("[INSUF", chunk_size=2))

    assert status == "answered"
    assert text == "[INSUF"


async def test_non_refusal_answer_still_streams_after_the_scan_window() -> None:
    # 判定窗口一结束就转入直通：整段回答必须逐字完整，不因为缓冲而丢字或重复。
    answer = "政近是因为家族安排离开的 [C17]。"

    text, status = await _answer_text_and_status(_marker_chat(answer, chunk_size=1))

    assert status == "answered"
    assert text == answer


# ---- provider 故障不降级成拒答 --------------------------------------------


async def test_provider_timeout_becomes_rag_timeout_not_refusal() -> None:
    assembled = [_assembled(_key(17), 17)]
    runner, _ = _runner(
        outcome=_outcome(assembled),
        chunks=[_context(17, _key(17))],
        chat=PartialThenFailingChat(),
    )

    events = await _events(runner)
    names = [event.name for event in events]

    assert names[-1] is EventName.QUERY_ERROR
    assert names.count(EventName.QUERY_ERROR) == 1
    assert EventName.QUERY_DONE not in names
    assert "insufficient_evidence" not in json.dumps(
        [event.payload for event in events], ensure_ascii=False
    )
    error = events[-1].payload
    assert error["code"] == "RAG_TIMEOUT"

    with pytest.raises(RagTimeout) as caught:
        await JsonResponseAdapter.fold(_replay(events), request_id=REQUEST_ID)
    assert caught.value.http_status == 504

    frames = [
        frame async for frame in SseResponseAdapter.stream(_replay(events), request_id=REQUEST_ID)
    ]
    event_name, data = parse_sse_frames(frames[-1])[0]
    assert event_name == "error"
    assert json.loads(data)["code"] == "RAG_TIMEOUT"
    assert all("[DONE]" not in frame for frame in frames)


async def test_retrieval_provider_error_becomes_502(image_root) -> None:
    runner, _ = _runner(
        retrieval_error=ProviderError("百炼返回 HTTP 500", provider="ali", status_code=500)
    )

    events = await _events(runner)

    assert [event.name for event in events] == [
        EventName.QUERY_STARTED,
        EventName.QUERY_ERROR,
    ]
    assert events[-1].payload["code"] == "RAG_PROVIDER_ERROR"

    with pytest.raises(RagProviderError) as caught:
        await JsonResponseAdapter.fold(_replay(events), request_id=REQUEST_ID)
    assert caught.value.http_status == 502

    client: TestClient = build_client_with_runner(image_root, runner)
    response = client.post(
        "/internal/v1/rag/query",
        json={"book_id": 1, "question": "问题", "level": "full"},
    )
    assert response.status_code == 502
    assert response.json()["code"] == "RAG_PROVIDER_ERROR"


async def test_missing_context_chunk_fails_loudly() -> None:
    # 装配集里的 chunk 在库里取不到正文：显式失败，不当成空上下文去拒答。
    assembled = [_assembled(_key(17), 17), _assembled(_key(45), 45)]

    class DroppingContext(StubContext):
        def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
            loaded = super().load(book_id, chunk_keys)
            return [chunk for chunk in loaded if chunk.chapter_index == 17]

    runner, _ = _runner(
        outcome=_outcome(assembled),
        context=DroppingContext([_context(17, _key(17)), _context(45, _key(45))]),
    )

    events = await _events(runner)

    assert [event.name for event in events] == [
        EventName.QUERY_STARTED,
        EventName.REALM_RESOLVED,
        EventName.RETRIEVAL_COMPLETED,
        EventName.RERANK_COMPLETED,
        EventName.CONTEXT_ASSEMBLED,
        EventName.QUERY_ERROR,
    ]
    with pytest.raises(RagUnavailable) as caught:
        await JsonResponseAdapter.fold(_replay(events), request_id=REQUEST_ID)
    assert caught.value.http_status == 503


# ---- 服务端不改写模型输出 --------------------------------------------------


async def test_model_output_is_forwarded_verbatim_even_with_out_of_range_citations() -> None:
    # 越界引用原样保留：不设引用白名单过滤、不剔除越界引用（M0-04 §4）。
    # 这条断言防止后来者「顺手加过滤」——过滤只覆盖带引用的越界，覆盖不了真正的泄漏路径。
    answer = "政近离开了 [C99]，文中还出现 [C017] 与 [c17]，以及 [C17,C45]。"
    runner, _ = _runner(
        outcome=_outcome([_assembled(_key(17), 17)]),
        chunks=[_context(17, _key(17))],
        chat=FakeChatModel(answer=answer, chunk_size=3),
    )

    events = await _events(runner)
    forwarded = "".join(
        event.payload["text"] for event in events if event.name is EventName.ANSWER_DELTA
    )

    assert forwarded == answer
    assert "[C99]" in forwarded
    assert "[C017]" in forwarded
    assert "[c17]" in forwarded
    assert "[C17,C45]" in forwarded


async def test_context_chapters_are_deduplicated_and_sorted_by_chapter() -> None:
    # 一段在第 45 章、两段在第 17 章；context_chapters 只按章出现一次且升序。
    assembled = [
        _assembled(_key(45), 45, rank=1),
        _assembled(_key(17, 0), 17, chunk_index=0, rank=2),
        _assembled(_key(17, 1), 17, chunk_index=1, source="neighbor", rank=2),
    ]
    runner, _ = _runner(
        outcome=_outcome(assembled),
        chunks=[
            _context(45, _key(45)),
            _context(17, _key(17, 0)),
            _context(17, _key(17, 1)),
        ],
    )

    events = await _events(runner)
    done = next(event for event in events if event.name is EventName.QUERY_DONE)

    assert done.payload["context_chapters"] == [
        {"chapter_index": 17, "chapter_title": "第17章 标题"},
        {"chapter_index": 45, "chapter_title": "第45章 标题"},
    ]


async def test_streaming_route_emits_full_sequence_and_done(image_root) -> None:
    runner, _ = _answered_case()
    client: TestClient = build_client_with_runner(image_root, runner)

    response = client.post(
        "/internal/v1/rag/query-stream",
        json={"book_id": 1, "question": "问题", "level": "full"},
        headers={"X-Request-Id": REQUEST_ID},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    assert frames[0][0] == "query_started"
    assert frames[1][0] == "realm_resolved"
    assert frames[-1] == (None, "[DONE]")
    assert frames[-2][0] == "query_done"


def _replay(events: Sequence[RagEvent]) -> AsyncIterator[RagEvent]:
    async def generator() -> AsyncIterator[RagEvent]:
        for event in events:
            yield event

    return generator()

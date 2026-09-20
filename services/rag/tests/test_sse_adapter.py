"""适配器单测：SSE 帧编码、终止规则、JSON 折叠。

事件序列是假数据，但编码路径与线上完全一致——JSON 适配器会丢弃全部中间事件，
中间事件的编码只能经 SSE 这条路径验证。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from helpers import REQUEST_ID, FailingQueryRunner, fake_event_sequence, parse_sse_frames
from omniread.api.adapters import DONE_FRAME, JsonResponseAdapter, SseResponseAdapter, encode_frame
from omniread.domain.errors import RagTimeout, RagUnavailable, error_from_wire
from omniread.domain.events import EVENT_ORDER, EventName, RagEvent, query_error
from omniread.domain.models import QueryRequest, RealmLevel


async def _from_list(events: list[RagEvent]) -> AsyncIterator[RagEvent]:
    for event in events:
        yield event


async def _collect_frames(events: AsyncIterator[RagEvent], request_id: str) -> list[str]:
    return [frame async for frame in SseResponseAdapter.stream(events, request_id=request_id)]


async def test_success_stream_encodes_every_event_then_done() -> None:
    frames = await _collect_frames(_from_list(fake_event_sequence()), REQUEST_ID)
    parsed = [parse_sse_frames(frame)[0] for frame in frames]
    names = [event for event, _ in parsed]

    expected = [event.name.value for event in fake_event_sequence()]
    assert names == [*expected, None]
    assert parsed[-1][1] == "[DONE]"
    assert frames[-1] == DONE_FRAME


async def test_success_stream_event_order_matches_contract() -> None:
    names = [event.name for event in fake_event_sequence()]

    assert names[0] is EVENT_ORDER[0]
    assert names[-1] is EVENT_ORDER[-1]
    # answer_delta 只能在 generation_started 之后；citation_ready 在生成结束后。
    assert names.count(EventName.ANSWER_DELTA) == 2
    first_delta = names.index(EventName.ANSWER_DELTA)
    assert names.index(EventName.GENERATION_STARTED) < first_delta
    assert first_delta < names.index(EventName.CITATION_READY)
    # 检索阶段四步全部发生在 generation_started 之前。
    assert names.index(EventName.CONTEXT_ASSEMBLED) < names.index(EventName.GENERATION_STARTED)


async def test_answer_delta_keeps_newlines_inside_one_data_line() -> None:
    frames = await _collect_frames(_from_list(fake_event_sequence()), REQUEST_ID)
    delta_frames = [frame for frame in frames if frame.startswith("event: answer_delta")]
    assert len(delta_frames) == 2

    data_lines = [
        line for frame in delta_frames for line in frame.split("\n") if line.startswith("data: ")
    ]
    assert len(data_lines) == 2
    texts = [json.loads(line[len("data: ") :])["text"] for line in data_lines]
    assert texts == ["政近离开了周防家。", "\n\n依据 [C17]。"]
    # 正文里的换行不得变成帧分隔，否则客户端会多切出一帧。
    assert "政近离开了周防家。" in delta_frames[0]


def test_encode_frame_is_single_data_line_then_blank_line() -> None:
    frame = encode_frame("answer_delta", {"text": "第一行\n第二行"})

    lines = frame.split("\n")
    assert lines[0] == "event: answer_delta"
    assert lines[1].startswith("data: ")
    assert lines[2:] == ["", ""]
    # 正文里的换行在 data 行里被转义，帧结构不会被撑破。
    assert "\\n" in lines[1]


async def test_query_error_is_encoded_as_error_event_without_done() -> None:
    event = query_error(request_id=REQUEST_ID, code="RAG_UNAVAILABLE", message="RAG 管线未实现")
    frames = await _collect_frames(_from_list([event]), REQUEST_ID)

    assert len(frames) == 1
    event_name, data = parse_sse_frames(frames[0])[0]
    assert event_name == "error"
    assert json.loads(data) == {
        "request_id": REQUEST_ID,
        "code": "RAG_UNAVAILABLE",
        "message": "RAG 管线未实现",
    }
    assert "[DONE]" not in frames[0]


async def test_rag_error_raised_midstream_becomes_error_frame() -> None:
    events = fake_event_sequence()[:6]
    runner = FailingQueryRunner(RagTimeout("provider 超时"), events)
    request = QueryRequest(book_id=1, question="q", level=RealmLevel.PAST)
    frames = await _collect_frames(runner.run(request, REQUEST_ID), REQUEST_ID)

    event_name, data = parse_sse_frames(frames[-1])[0]
    assert event_name == "error"
    assert json.loads(data)["code"] == "RAG_TIMEOUT"
    assert all("[DONE]" not in frame for frame in frames)


async def test_json_adapter_folds_stream_into_single_object() -> None:
    response = await JsonResponseAdapter.fold(
        _from_list(fake_event_sequence()), request_id=REQUEST_ID
    )

    assert response.request_id == REQUEST_ID
    assert response.status == "answered"
    assert response.answer == "政近离开了周防家。\n\n依据 [C17]。"
    assert [chapter.chapter_index for chapter in response.context_chapters] == [17]
    assert response.usage.answer_model == "glm-5.3-flash"


async def test_json_adapter_raises_mapped_error_on_query_error() -> None:
    event = query_error(request_id=REQUEST_ID, code="RAG_TIMEOUT", message="provider 超时")
    with pytest.raises(RagTimeout) as caught:
        await JsonResponseAdapter.fold(_from_list([event]), request_id=REQUEST_ID)
    assert caught.value.http_status == 504


async def test_json_adapter_rejects_stream_without_terminal_event() -> None:
    with pytest.raises(RagUnavailable):
        await JsonResponseAdapter.fold(
            _from_list(fake_event_sequence()[:3]), request_id=REQUEST_ID
        )


def test_unknown_error_code_maps_to_unavailable() -> None:
    error = error_from_wire("RAG_SOMETHING_NEW", "越界取值")
    assert isinstance(error, RagUnavailable)
    assert error.code.value == "RAG_UNAVAILABLE"

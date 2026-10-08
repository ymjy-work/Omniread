"""答案层确定性判定：引用越界、拒答正确性、状态折叠（M1-2）。

不调模型、不连库：判据全是字符串与集合运算，喂进去什么就判什么。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from omniread.domain.events import (
    AnswerStatus,
    answer_delta,
    citation_ready,
    query_done,
    query_error,
    query_started,
)
from omniread.pipelines.evaluation.generation import (
    AnswerOutcome,
    aggregate_generation,
    fold_answer,
    generation_failure_rows,
    score_answer,
)
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_GENERATION_FAILED,
    STATUS_INSUFFICIENT_EVIDENCE,
    GenerationScoreRecord,
)

QUESTION = {
    "id": "fact-001",
    "type": "fact",
    "difficulty": "easy",
    "level": "past",
    "progress": 4,
    "question": "艾莉为什么说俄语？",
    "expect_refusal": False,
}

#: 装配集涉及第 17 章与第 45 章——也就是本次允许引用的章号。
CHAPTERS = (17, 45)


def _answer(text: str, *, status: str = STATUS_ANSWERED, chapters: tuple[int, ...] = CHAPTERS):
    return AnswerOutcome(
        request_id="eval-fact-001", status=status, text=text, chapters=chapters
    )


def _score(question: dict, answer: AnswerOutcome) -> GenerationScoreRecord:
    return score_answer(
        question,
        answer,
        answer_provider="fake",
        answer_model="fake-chat",
        prompt_version="deadbeef1234",
    )


# ---- 引用越界 --------------------------------------------------------------


def test_citations_inside_the_assembled_set_pass() -> None:
    record = _score(QUESTION, _answer("政近离开了 [C17]，艾莉留了下来 [C45]。"))

    assert record.citation_in_set is True
    assert record.citation_out_of_range == ()
    assert record.citation_count == 2
    assert record.citation_malformed_count == 0


def test_out_of_range_citation_is_rebuilt_from_the_chapter_number() -> None:
    # 记的是**重拼**出来的标记，不是从答案里切下来的片段：
    # `CANDIDATE_PATTERN` 的 `[^\\]]*` 能把一整段正文裹进候选里。
    record = _score(QUESTION, _answer("政近离开了 [C99]。"))

    assert record.citation_in_set is False
    assert record.citation_out_of_range == ("[C99]",)


def test_duplicate_out_of_range_citations_are_recorded_once() -> None:
    record = _score(QUESTION, _answer("看 [C99]，再看 [C99]，还有 [C99]。"))

    assert record.citation_out_of_range == ("[C99]",)


def test_out_of_range_markers_never_carry_surrounding_prose() -> None:
    # `[C7 这段说明很长很长……]` 不是规范引用，进的是「非规范写法」的**条数**，
    # 而不是越界列表——那条列表里的每一项都会进 git。
    record = _score(QUESTION, _answer("他说 [C7 这段说明很长很长] 就没了。"))

    assert record.citation_out_of_range == ()
    assert record.citation_count == 0
    assert record.citation_malformed_count == 1


def test_answer_without_any_citation_passes_the_set_check_vacuously() -> None:
    # 空集天然满足集合判定——所以聚合必须把「一条引用都没有」单列出来，
    # 否则一个从不标注引用的回答会带着满分通过。
    record = _score(QUESTION, _answer("政近离开了，文中没有直接说明原因。"))

    assert record.citation_in_set is True
    assert record.citation_count == 0


def test_chapters_come_from_the_assembled_set_not_from_the_answer() -> None:
    # 同一段文本，允许集不同则结论不同：判据只有「引用是否落在装配集内」。
    text = "见 [C45]。"

    assert _score(QUESTION, _answer(text, chapters=(45,))).citation_in_set is True
    assert _score(QUESTION, _answer(text, chapters=(17,))).citation_in_set is False


# ---- 事件流折叠 ------------------------------------------------------------


def _stream(*, status: AnswerStatus, chapters: list[dict]) -> list:
    return [
        query_started(request_id="eval-fact-001", book_id=1, level="past", progress=4),
        answer_delta(text="政近"),
        answer_delta(text="离开了 [C17]。"),
        citation_ready(context_chapters=chapters),
        query_done(status=status, context_chapters=chapters, usage={}),
    ]


def test_fold_status_strings_match_the_record_statuses() -> None:
    # 事件流用 `AnswerStatus` 枚举，逐题记录用字符串常量。两处各写一份字面量，
    # 拼错一个字母就会让「这次 run 有几条拒答」静默变成 0。
    assert AnswerStatus.ANSWERED.value == STATUS_ANSWERED
    assert AnswerStatus.INSUFFICIENT_EVIDENCE.value == STATUS_INSUFFICIENT_EVIDENCE


def test_fold_answered_stream_joins_deltas_and_reads_chapters() -> None:
    chapters = [{"chapter_index": 17, "chapter_title": "第17章"}]

    outcome = fold_answer(_stream(status=AnswerStatus.ANSWERED, chapters=chapters))

    assert outcome.status == STATUS_ANSWERED
    assert outcome.text == "政近离开了 [C17]。"
    assert outcome.chapters == (17,)
    assert outcome.request_id == "eval-fact-001"


def test_fold_refusal_stream_keeps_the_context_chapters() -> None:
    # §8.3：模型级拒答时 `context_chapters` **非空**——折叠不能把它清掉，
    # 否则判「该拒的拒了没有」时就分不出「检索为空」与「模型答不了」。
    chapters = [{"chapter_index": 17, "chapter_title": "第17章"}]

    outcome = fold_answer(
        _stream(status=AnswerStatus.INSUFFICIENT_EVIDENCE, chapters=chapters)
    )

    assert outcome.status == STATUS_INSUFFICIENT_EVIDENCE
    assert outcome.chapters == (17,)


def test_fold_query_error_is_generation_failed_not_refusal() -> None:
    # provider 故障绝不降级成拒答：记成拒答会让 `refusal_correct` 悄悄失真。
    events = [
        query_started(request_id="eval-fact-001", book_id=1, level="past", progress=4),
        query_error(request_id="eval-fact-001", code="RAG_TIMEOUT", message="provider 超时"),
    ]

    outcome = fold_answer(events)

    assert outcome.status == STATUS_GENERATION_FAILED
    assert outcome.text == ""
    assert outcome.chapters == ()


# ---- 汇总 ------------------------------------------------------------------


def _record(
    question_id: str,
    *,
    status: str = STATUS_ANSWERED,
    in_set: bool = True,
    citations: int = 1,
    expect_refusal: bool = False,
    question_type: str = "fact",
) -> GenerationScoreRecord:
    return GenerationScoreRecord(
        question_id=question_id,
        question_type=question_type,
        difficulty="easy",
        expect_refusal=expect_refusal,
        status=status,
        citation_count=citations,
        citation_in_set=in_set,
        citation_out_of_range=() if in_set else ("[C99]",),
        citation_malformed_count=0,
        request_id=f"eval-{question_id}",
        answer_provider="fake",
        answer_model="fake-chat",
        prompt_version="deadbeef1234",
    )


def test_citation_denominator_excludes_refusals_and_failures() -> None:
    records = [
        _record("a"),
        _record("b", in_set=False),
        _record("c", status=STATUS_INSUFFICIENT_EVIDENCE, citations=0),
        _record("d", status=STATUS_GENERATION_FAILED, citations=0),
    ]

    summary = aggregate_generation(records)

    assert summary["question_count"] == 4
    assert summary["answered"] == 2
    assert summary["citation_in_set_denominator"] == 2
    assert summary["citation_in_set"] == 0.5
    assert summary["generation_failed"] == 1


def test_answered_without_citation_is_reported_next_to_the_ratio() -> None:
    # 三条都「通过」集合判定，但两条根本没标引用——只看 `citation_in_set` 会读成满分。
    records = [_record("a"), _record("b", citations=0), _record("c", citations=0)]

    summary = aggregate_generation(records)

    assert summary["citation_in_set"] == 1.0
    assert summary["answered_without_citation"] == 2


def test_refusal_correct_keeps_failures_in_the_denominator() -> None:
    records = [
        _record("s1", status=STATUS_INSUFFICIENT_EVIDENCE, expect_refusal=True),
        _record("s2", status=STATUS_ANSWERED, expect_refusal=True),
        # 生成失败既不是正确拒答，也不能从分母里剔掉——剔了就是让指标随故障变好看。
        _record("s3", status=STATUS_GENERATION_FAILED, expect_refusal=True),
    ]

    summary = aggregate_generation(records)

    assert summary["refusal_denominator"] == 3
    assert summary["refusal_correct"] == pytest.approx(1 / 3)


def test_refusal_false_positive_blocks_the_refuse_everything_solution() -> None:
    # 「见谁都拒答」在 `refusal_correct` 上拿满分，必须由这一项戳穿。
    records = [
        _record("s1", status=STATUS_INSUFFICIENT_EVIDENCE, expect_refusal=True),
        _record("n1", status=STATUS_INSUFFICIENT_EVIDENCE),
        _record("n2", status=STATUS_INSUFFICIENT_EVIDENCE),
    ]

    summary = aggregate_generation(records)

    assert summary["refusal_correct"] == 1.0
    assert summary["refusal_false_positive"] == 2


def test_per_type_breakdown_carries_its_own_denominator() -> None:
    records = [
        _record("a", question_type="cross"),
        _record("b", question_type="cross", in_set=False),
        _record(
            "c",
            question_type="spoiler",
            expect_refusal=True,
            status=STATUS_INSUFFICIENT_EVIDENCE,
            citations=0,
        ),
    ]

    # 汇总字典的值是 `object`（它是产物形状，键集随口径增删）：这里显式收窄，
    # 免得把「分列结构变了」这件事降级成一条 mypy 报错。
    breakdown = cast(dict[str, dict[str, object]], aggregate_generation(records)["per_type"])

    assert breakdown["cross"] == {
        "questions": 2,
        "answered": 2,
        "citation_in_set": 0.5,
        "citation_in_set_denominator": 2,
        "generation_failed": 0,
    }
    assert breakdown["spoiler"]["citation_in_set_denominator"] == 0


def test_failure_rows_cover_generation_citation_and_refusal() -> None:
    records = [
        _record("ok"),
        _record("gen", status=STATUS_GENERATION_FAILED, citations=0),
        _record("cit", in_set=False),
        _record("ref", expect_refusal=True),
    ]

    stages = {row["question_id"]: row["stage"] for row in generation_failure_rows(records)}

    assert stages == {"gen": "generation", "cit": "citation", "ref": "refusal"}


# ---- 产物还原 --------------------------------------------------------------


def test_from_payload_rejects_an_unknown_status() -> None:
    payload = {
        "question_id": "a",
        "question_type": "fact",
        "difficulty": "easy",
        "expect_refusal": False,
        "status": "maybe",
        "citation_count": 0,
        "citation_in_set": True,
        "citation_out_of_range": [],
        "citation_malformed_count": 0,
        "request_id": "eval-a",
        "answer_provider": "fake",
        "answer_model": "fake-chat",
        "prompt_version": "deadbeef1234",
    }

    with pytest.raises(ValueError, match="status"):
        GenerationScoreRecord.from_payload(payload)


def test_from_payload_restores_tuples_and_rejects_bad_scalars() -> None:
    payload = {
        "question_id": "a",
        "question_type": "fact",
        "difficulty": "easy",
        "expect_refusal": False,
        "status": STATUS_ANSWERED,
        "citation_count": 1,
        "citation_in_set": False,
        "citation_out_of_range": ["[C99]"],
        "citation_malformed_count": 0,
        "request_id": "eval-a",
        "answer_provider": "fake",
        "answer_model": "fake-chat",
        "prompt_version": "deadbeef1234",
    }

    record = GenerationScoreRecord.from_payload(payload)
    assert record.citation_out_of_range == ("[C99]",)

    # 布尔是 `int` 的子类：`citation_in_set` 收下一个真值字符串就会让失败题算成通过。
    with pytest.raises(ValueError, match="citation_in_set"):
        GenerationScoreRecord.from_payload({**payload, "citation_in_set": "no"})

    with pytest.raises(ValueError, match="citation_out_of_range"):
        GenerationScoreRecord.from_payload({**payload, "citation_out_of_range": "[C99]"})


def test_record_is_frozen() -> None:
    record = _record("a")

    with pytest.raises(FrozenInstanceError):
        record.status = STATUS_ANSWERED  # type: ignore[misc]

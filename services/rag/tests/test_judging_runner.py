"""裁判层编排：材料回放、单题失败不中断、聚合口径。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from omniread.domain.models import ContextChunk
from omniread.pipelines.evaluation.generation import AnswerOutcome
from omniread.pipelines.evaluation.judging_runner import (
    JUDGE_STATUS_FAILED,
    JUDGE_STATUS_OK,
    JudgedAnswer,
    aggregate_judging,
    load_passages,
    run_judging_eval,
)
from omniread.pipelines.evaluation.runner import build_query_request
from omniread.pipelines.judging import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNCERTAIN,
    JudgeError,
    JudgeVerdict,
)

QUESTIONS = [
    {
        "id": "fact-101",
        "type": "fact",
        "question": "政近借的是哪一科的参考书？",
        "level": "past",
        "progress": 5,
        "expect_refusal": False,
    },
    {
        "id": "spoiler-101",
        "type": "spoiler",
        "question": "结局里谁去了海外？",
        "level": "past",
        "progress": 3,
        "expect_refusal": True,
    },
]

ANSWERS = (
    AnswerOutcome(request_id="eval-fact-101", status="answered", text="化学参考书[C2]。", chapters=(2,)),
    AnswerOutcome(request_id="eval-spoiler-101", status="answered", text="[INSUFFICIENT]", chapters=(3,)),
)

CHUNKS = (
    ContextChunk(chunk_key="k2", chapter_index=2, chapter_title="第2话", text="他借了化学参考书。"),
    ContextChunk(chunk_key="k3", chapter_index=3, chapter_title="第3话", text="那天很热。"),
)


class StubContext:
    """只回手上那几块正文的假 ContextSource。`drop` 用来模拟「库与检索视图不一致」。"""

    def __init__(self, chunks=CHUNKS, drop: frozenset[str] = frozenset()) -> None:
        self._chunks = [chunk for chunk in chunks if chunk.chunk_key not in drop]

    def load(self, book_id: int, keys):
        wanted = set(keys)
        return [chunk for chunk in self._chunks if chunk.chunk_key in wanted]


class StubJudge:
    """按题号决定判定或抛错的假裁判。"""

    provider = "stub"
    model = "stub-judge"
    prompt_version = "0" * 12

    def __init__(self, verdict: JudgeVerdict, fail_on: frozenset[str] = frozenset()) -> None:
        self.verdict = verdict
        self.fail_on = fail_on
        self.calls: list[tuple[str, list[int], str]] = []

    async def judge(self, question, passages, answer):
        self.calls.append((question, [item.chapter_index for item in passages], answer))
        if question in self.fail_on:
            raise JudgeError("裁判输出不是合法 JSON")
        return self.verdict


def verdict(verdict_name: str = VERDICT_PASS, **overrides: object) -> JudgeVerdict:
    fields: dict[str, object] = {
        "verdict": verdict_name,
        "supported": True,
        "citations_valid": True,
        "complete": True,
        "refusal_correct": True,
        "issues": (),
        "reason": "材料支持该结论",
        "raw": '{"verdict": "PASS"}',
    }
    fields.update(overrides)
    return JudgeVerdict(**fields)  # type: ignore[arg-type]


def retrieval_for(question: dict, keys: tuple[str, ...]):
    """按 `build_query_request` 建键——**与答案层用的是同一个函数**，所以查得到。"""
    request = build_query_request(question, book_id=1)
    return {request: SimpleNamespace(assembled=[SimpleNamespace(chunk_key=k) for k in keys])}


# ── 材料回放 ──


async def test_passages_come_back_in_assembly_order() -> None:
    retrieval = retrieval_for(QUESTIONS[0], ("k3", "k2"))

    passages = await load_passages(
        QUESTIONS[0],
        retrieval=retrieval,
        context=StubContext(),
        book_id=1,
        neighbor_expand=True,
    )

    # 顺序即装配顺序，不是 chunk_key 序——裁判看到的材料要与回答逐字同序。
    assert [item.chapter_index for item in passages] == [3, 2]
    assert passages[0].text == "那天很热。"


async def test_unknown_request_is_an_error_not_empty_material() -> None:
    """查不到就报错：静默退回空材料会把「检索结果丢了」伪装成「裁判看到材料不足」。"""
    with pytest.raises(LookupError):
        await load_passages(
            QUESTIONS[0],
            retrieval={},
            context=StubContext(),
            book_id=1,
            neighbor_expand=True,
        )


async def test_missing_chunk_text_is_an_error() -> None:
    retrieval = retrieval_for(QUESTIONS[0], ("k2",))

    with pytest.raises(LookupError):
        await load_passages(
            QUESTIONS[0],
            retrieval=retrieval,
            context=StubContext(drop=frozenset({"k2"})),
            book_id=1,
            neighbor_expand=True,
        )


async def test_empty_assembly_yields_no_passages() -> None:
    retrieval = retrieval_for(QUESTIONS[0], ())

    assert (
        await load_passages(
            QUESTIONS[0],
            retrieval=retrieval,
            context=StubContext(),
            book_id=1,
            neighbor_expand=True,
        )
        == []
    )


# ── 编排 ──


async def test_answers_and_questions_must_line_up() -> None:
    with pytest.raises(ValueError):
        await run_judging_eval(
            questions=QUESTIONS,
            answers=ANSWERS[:1],
            retrieval=retrieval_for(QUESTIONS[0], ("k2",)),
            context=StubContext(),
            judge=StubJudge(verdict()),
        )


async def test_each_question_is_judged_with_its_own_material() -> None:
    retrieval = {**retrieval_for(QUESTIONS[0], ("k2",)), **retrieval_for(QUESTIONS[1], ("k3",))}
    judge = StubJudge(verdict())
    result = await run_judging_eval(
        questions=QUESTIONS, answers=ANSWERS, retrieval=retrieval, context=StubContext(), judge=judge
    )

    assert [item.question_id for item in result.verdicts] == ["fact-101", "spoiler-101"]
    assert judge.calls[0] == ("政近借的是哪一科的参考书？", [2], "化学参考书[C2]。")
    assert judge.calls[1] == ("结局里谁去了海外？", [3], "[INSUFFICIENT]")
    assert result.summary["judged"] == 2


async def test_one_failed_question_does_not_abort_the_round() -> None:
    """单题判不出来不能整轮作废——整轮作废的代价是全部真实调用白花。"""
    retrieval = {**retrieval_for(QUESTIONS[0], ("k2",)), **retrieval_for(QUESTIONS[1], ("k3",))}
    result = await run_judging_eval(
        questions=QUESTIONS,
        answers=ANSWERS,
        retrieval=retrieval,
        context=StubContext(),
        # 桩按**题面文本**匹配：裁判收到的是题面，不是题号。
        judge=StubJudge(verdict(), fail_on=frozenset({"政近借的是哪一科的参考书？"})),
    )

    failed, ok = result.verdicts
    assert failed.status == JUDGE_STATUS_FAILED
    assert failed.verdict == ""
    assert "JudgeError" in failed.reason
    assert ok.status == JUDGE_STATUS_OK
    assert result.summary["judge_failed"] == 1
    assert result.summary["judged"] == 1


# ── 聚合口径 ──


def judged(verdict_name: str, question_type: str = "fact", **overrides: object) -> JudgedAnswer:
    fields: dict[str, object] = {
        "question_id": "q",
        "question_type": question_type,
        "expect_refusal": False,
        "status": JUDGE_STATUS_OK,
        "verdict": verdict_name,
        "supported": True,
        "citations_valid": True,
        "complete": True,
        "refusal_correct": True,
        "issues": (),
        "reason": "",
        "raw": "",
    }
    fields.update(overrides)
    return JudgedAnswer(**fields)  # type: ignore[arg-type]


def test_aggregate_counts_the_three_states() -> None:
    summary = aggregate_judging(
        [
            judged(VERDICT_PASS),
            judged(VERDICT_FAIL, supported=False),
            judged(VERDICT_UNCERTAIN),
        ]
    )

    assert summary["judged"] == 3
    assert (summary["pass"], summary["fail"], summary["uncertain"]) == (1, 1, 1)
    assert summary["supported_false"] == 1


def test_failed_questions_stay_out_of_the_ratio_denominator() -> None:
    """判不出来的题不进分母——否则「裁判坏了一半」会显示成一个偏低的通过率。"""
    summary = aggregate_judging(
        [
            judged(VERDICT_PASS),
            judged(VERDICT_PASS),
            judged("", status=JUDGE_STATUS_FAILED),
        ]
    )

    assert summary["judged"] == 2
    assert summary["judge_failed"] == 1
    assert summary["pass"] == 2


def test_aggregate_splits_by_question_type() -> None:
    summary = aggregate_judging(
        [
            judged(VERDICT_PASS, question_type="cross"),
            judged(VERDICT_FAIL, question_type="cross"),
            judged("", question_type="spoiler", status=JUDGE_STATUS_FAILED),
        ]
    )

    per_type = summary["per_type"]
    assert per_type["cross"] == {"judged": 2, "pass": 1, "fail": 1, "uncertain": 0, "judge_failed": 0}
    assert per_type["spoiler"] == {"judged": 0, "pass": 0, "fail": 0, "uncertain": 0, "judge_failed": 1}


def test_refusal_wrong_counts_both_directions() -> None:
    """`refusal_correct=False` 一个数涵盖两个方向：该拒没拒、不该拒却拒了。"""
    summary = aggregate_judging(
        [
            judged(VERDICT_FAIL, refusal_correct=False),
            judged(VERDICT_FAIL, refusal_correct=False),
        ]
    )

    assert summary["refusal_wrong"] == 2

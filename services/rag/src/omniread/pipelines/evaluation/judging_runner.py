"""裁判层评测编排：逐题把「材料 + 问题 + 回答」交给裁判，收一份旁挂的判定。

**它旁挂在确定性指标旁边，不作门禁**（`M0-04` §6、`M0-05` 外部共识「An LLM judge
cannot be a build gate」）：模型判断重跑分数会变，回归与测量噪声分不开，门禁会误报
然后被人关掉。所以这里产出的数字**不进** `summary.json`，只落 `temp/`——run 目录进 git，
而裁判的 `reason` 是自由文本、会逐字引用材料（`M0-02` §7.1）。

**材料必须与回答看到的那一份逐字相同**：所以这里不重跑检索，而是从本次 run 已经算好的
`RetrievalOutcome`（`assembled[].chunk_key`）按同一个 `ContextSource` 取回正文——
与 `AnsweringRunner._load_context` 同一条路径、同一个顺序。裁判看的是别的材料，
它的判定就不再描述「模型当时看到了什么」。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from omniread.application.ports import ContextSource
from omniread.domain.errors import RagError
from omniread.domain.models import QueryRequest
from omniread.infrastructure.providers.errors import ProviderError
from omniread.pipelines.answering.prompt import ContextPassage
from omniread.pipelines.evaluation.generation import AnswerOutcome
from omniread.pipelines.evaluation.runner import build_query_request
from omniread.pipelines.judging import VERDICT_FAIL, VERDICT_PASS, VERDICT_UNCERTAIN, JudgeError
from omniread.pipelines.retrieval.types import RetrievalOutcome

#: 假裁判的判定与材料无关，`judging` 一节的所有数字都只是「链路通了」的证据。
FAKE_JUDGE_TRUST_NOTE = (
    "本次跑用确定性假裁判：判定与材料无关，judging 一节的数字不可作为基线。"
)

JUDGE_STATUS_OK = "ok"
JUDGE_STATUS_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JudgedAnswer:
    """一题的裁判结果。

    `reason` / `issues` / `raw` 是裁判的自由文本，**会逐字引用材料**，所以只随复核件
    落 `temp/`；聚合数字只数那四个布尔与三态，不碰文本。
    """

    question_id: str
    question_type: str
    expect_refusal: bool
    status: str
    verdict: str
    supported: bool | None
    citations_valid: bool | None
    complete: bool | None
    refusal_correct: bool | None
    issues: tuple[str, ...]
    reason: str
    raw: str

    @property
    def passed(self) -> bool:
        return self.status == JUDGE_STATUS_OK and self.verdict == VERDICT_PASS


@dataclass(frozen=True, slots=True)
class JudgingEvalResult:
    verdicts: tuple[JudgedAnswer, ...]
    summary: dict[str, object]


async def run_judging_eval(
    *,
    questions: Sequence[Mapping[str, object]],
    answers: Sequence[AnswerOutcome],
    retrieval: Mapping[QueryRequest, RetrievalOutcome],
    context: ContextSource,
    judge: object,
    book_id: int = 1,
    neighbor_expand: bool = True,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> JudgingEvalResult:
    """逐题判一遍。题目顺序与答案顺序必须一一对应（答案层就是这么产出的）。

    **单题失败不中断整轮**：裁判的格式问题、provider 抖动都会让某题判不出来，而整轮
    作废的代价是全部真实调用白花。失败逐题记 `status=failed` 并计数上报——不静默，
    也不把失败当成一个「看起来正常的判定」混进统计。
    """
    if len(answers) != len(questions):
        raise ValueError(
            f"答案数（{len(answers)}）与题数（{len(questions)}）对不上："
            "答案层与裁判层必须跑同一批题"
        )

    verdicts: list[JudgedAnswer] = []
    total = len(questions)
    for index, (question, answer) in enumerate(
        zip(questions, answers, strict=True), start=1
    ):
        question_id = str(question["id"])
        if on_progress is not None:
            on_progress(index, total, question_id)
        question_type = str(question["type"])
        expect_refusal = bool(question["expect_refusal"])
        try:
            passages = await load_passages(
                question,
                retrieval=retrieval,
                context=context,
                book_id=book_id,
                neighbor_expand=neighbor_expand,
            )
            verdict = await judge.judge(  # type: ignore[attr-defined]
                str(question["question"]), passages, answer.text
            )
        except (JudgeError, ProviderError, RagError, LookupError) as failure:
            verdicts.append(
                JudgedAnswer(
                    question_id=question_id,
                    question_type=question_type,
                    expect_refusal=expect_refusal,
                    status=JUDGE_STATUS_FAILED,
                    verdict="",
                    supported=None,
                    citations_valid=None,
                    complete=None,
                    refusal_correct=None,
                    issues=(),
                    reason=f"{type(failure).__name__}: {failure}",
                    raw="",
                )
            )
            continue
        verdicts.append(
            JudgedAnswer(
                question_id=question_id,
                question_type=question_type,
                expect_refusal=expect_refusal,
                status=JUDGE_STATUS_OK,
                verdict=verdict.verdict,
                supported=verdict.supported,
                citations_valid=verdict.citations_valid,
                complete=verdict.complete,
                refusal_correct=verdict.refusal_correct,
                issues=verdict.issues,
                reason=verdict.reason,
                raw=verdict.raw,
            )
        )

    frozen = tuple(verdicts)
    return JudgingEvalResult(verdicts=frozen, summary=aggregate_judging(frozen))


async def load_passages(
    question: Mapping[str, object],
    *,
    retrieval: Mapping[QueryRequest, RetrievalOutcome],
    context: ContextSource,
    book_id: int,
    neighbor_expand: bool,
) -> list[ContextPassage]:
    """按装配顺序取回这一题的材料正文。

    请求按 `build_query_request` 重建——**与答案层用的是同一个函数**，所以查得到；
    查不到即报错，不静默退回空材料（那会把「这次 run 的检索结果丢了」伪装成
    「裁判看到材料不足而拒答」）。
    """
    request = build_query_request(question, book_id=book_id, neighbor_expand=neighbor_expand)
    try:
        outcome = retrieval[request]
    except KeyError:
        raise LookupError(
            f"检索结果里没有这一条请求：{request.question!r}"
            "（level / progress / neighbor_expand 任一不同都算另一次请求）"
        ) from None

    keys = [item.chunk_key for item in outcome.assembled]
    if not keys:
        return []
    loaded = await asyncio.to_thread(context.load, book_id, keys)
    by_key = {chunk.chunk_key: chunk for chunk in loaded}
    missing = [key for key in keys if key not in by_key]
    if missing:
        raise LookupError(f"装配上下文缺少 {len(missing)} 个 chunk 正文")
    return [
        ContextPassage(chapter_index=by_key[key].chapter_index, text=by_key[key].text)
        for key in keys
    ]


def aggregate_judging(verdicts: Sequence[JudgedAnswer]) -> dict[str, object]:
    """把逐题判定折成聚合数字。**只数三态与四个布尔，不碰自由文本。**

    `judge_failed` 与 `judged` 必须并读：`pass` 的分母是 `judged` 而不是题数，
    判不出来的题不参与比率——否则「裁判坏了一半」会显示成一个偏低的通过率。
    """
    judged = [item for item in verdicts if item.status == JUDGE_STATUS_OK]
    failed = [item for item in verdicts if item.status == JUDGE_STATUS_FAILED]
    per_type: dict[str, dict[str, int]] = {}
    for item in verdicts:
        bucket = per_type.setdefault(
            item.question_type,
            {"judged": 0, "pass": 0, "fail": 0, "uncertain": 0, "judge_failed": 0},
        )
        if item.status == JUDGE_STATUS_FAILED:
            bucket["judge_failed"] += 1
            continue
        bucket["judged"] += 1
        if item.verdict == VERDICT_PASS:
            bucket["pass"] += 1
        elif item.verdict == VERDICT_FAIL:
            bucket["fail"] += 1
        elif item.verdict == VERDICT_UNCERTAIN:
            bucket["uncertain"] += 1

    return {
        "question_count": len(verdicts),
        "judged": len(judged),
        "judge_failed": len(failed),
        "pass": sum(1 for item in judged if item.verdict == VERDICT_PASS),
        "fail": sum(1 for item in judged if item.verdict == VERDICT_FAIL),
        "uncertain": sum(1 for item in judged if item.verdict == VERDICT_UNCERTAIN),
        # 四个布尔各自「判为否」的条数：它们比总判定更能指出错在哪一类。
        "supported_false": sum(1 for item in judged if item.supported is False),
        "citations_invalid": sum(1 for item in judged if item.citations_valid is False),
        "incomplete": sum(1 for item in judged if item.complete is False),
        "refusal_wrong": sum(1 for item in judged if item.refusal_correct is False),
        "per_type": per_type,
    }


def judging_artifact(
    *,
    verdicts: Sequence[JudgedAnswer],
    summary: Mapping[str, object],
    provider: str,
    model: str,
    prompt_version: str,
) -> dict[str, object]:
    """裁判复核件的载荷：聚合 + 逐题。

    逐题那段直接 `asdict`，**不手抄一遍字段名**——手抄的那份会与 dataclass 漂，
    漂了之后要么少一个字段、要么多一个没人填的空列，而两种都不会报错。
    """
    return {
        "judge_provider": provider,
        "judge_model": model,
        "judge_prompt_version": prompt_version,
        "summary": dict(summary),
        "verdicts": [asdict(item) for item in verdicts],
    }


def write_judging_artifact(
    path: Path,
    *,
    verdicts: Sequence[JudgedAnswer],
    summary: Mapping[str, object],
    provider: str,
    model: str,
    prompt_version: str,
) -> None:
    """把复核件写盘。**调用方负责挡住「别写进 run 目录」**（`reason` 会引用材料）。"""
    payload = judging_artifact(
        verdicts=verdicts,
        summary=summary,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


__all__ = [
    "FAKE_JUDGE_TRUST_NOTE",
    "JUDGE_STATUS_FAILED",
    "JUDGE_STATUS_OK",
    "JudgedAnswer",
    "JudgingEvalResult",
    "aggregate_judging",
    "judging_artifact",
    "load_passages",
    "run_judging_eval",
    "write_judging_artifact",
]

"""答案层的**确定性**指标（M0-04 §5.2，M1-2）。

判据全部由程序算出，不调用模型判断（D1），因此可复现、可离线重算。三个数：

- **`citation_in_set`**：回答里的每一个 `[C数字]` 是否落在本次装配集的章号内。
  这是**评测指标，不是运行时过滤**——服务端不改写模型输出，越界引用如实保留（`M0-04` §4）。
- **`refusal_correct`**：`expect_refusal=true` 的题里，有多少条真的拒答了。
- **`refusal_false_positive`**：`expect_refusal=false` 的题里被拒答的条数。

第三个不是装饰：只看前两个，一个「什么都答不了」的模型会在 `refusal_correct` 上拿满分
——拒答的题它全对，其余题不判。这与引用侧那条老教训同形：集合判定对空集天然安全，
门禁／指标恒真就等于没有。

**分母单列**（与检索层同一条规矩）：`citation_in_set` 的分母是**真答出来的题**，
拒答题与生成失败的题不在其中——它们没有引用可判，算「通过」会虚高、算「失败」又不对。
代价是分母会随结果缩水，所以 `generation_failed` 与分母一起报，缩了多少一眼可见。

**已知盲区**（D1 的代价）：两段引用都在集合内、错在语义关系的那类错误（把第 9 章与
第 18 章的剧情焊成一条时间线）这里抓不到——`M1-backlog.md` 记着真实错例，
M1 内只能人工抽检。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from omniread.domain.citation import find_citations, find_violations
from omniread.domain.events import EventName, RagEvent
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_GENERATION_FAILED,
    STATUS_INSUFFICIENT_EVIDENCE,
    GenerationScoreRecord,
)

#: 拒答状态的两个来源（检索为空 / 模型级）在记录里是同一个值——`M0-02` §8.3 用
#: `context_chapters` 空不空区分它们，而拒答**正确性**只问「该拒的拒了没有」。
_REFUSAL_STATUSES = frozenset({STATUS_INSUFFICIENT_EVIDENCE})


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    """一次问答链跑完后的可判定量，全部从事件流折出来。

    `chapters` 取 `query_done` 报的 `context_chapters`——那正是契约里「本次允许引用的
    范围」，也是客户端用来把 `[C17]` 渲染成角标的同一份数据。
    """

    request_id: str
    status: str
    text: str
    chapters: tuple[int, ...]


def fold_answer(events: Sequence[RagEvent]) -> AnswerOutcome:
    """把一条事件流折成 `AnswerOutcome`。

    成功以 `query_done` 收尾、失败以 `query_error` 收尾，两者互斥（`M0-02` §8.5）。
    `query_error` 一律记 `generation_failed`：provider 故障不降级成拒答，记成拒答会让
    `refusal_correct` 跟着失真。

    检索阶段就失败的 provider 故障也落进同一个状态——对答案层来说两者都是「这题没有
    答案，这次 run 要重跑」，`error_code` 在原事件里，不进产物。
    """
    text_parts: list[str] = []
    chapters: tuple[int, ...] = ()
    status = STATUS_GENERATION_FAILED

    for event in events:
        if event.name is EventName.ANSWER_DELTA:
            text_parts.append(str(event.payload["text"]))
        elif event.name is EventName.QUERY_DONE:
            status = str(event.payload["status"])
            chapters = tuple(
                chapter["chapter_index"] for chapter in event.payload["context_chapters"]
            )
        elif event.name is EventName.QUERY_ERROR:
            return AnswerOutcome(
                request_id=str(event.payload.get("request_id", "")),
                status=STATUS_GENERATION_FAILED,
                text="",
                chapters=(),
            )

    request_id = events[0].payload.get("request_id", "") if events else ""
    return AnswerOutcome(
        request_id=str(request_id), status=status, text="".join(text_parts), chapters=chapters
    )


def score_answer(
    question: Mapping[str, Any],
    answer: AnswerOutcome,
    *,
    answer_provider: str,
    answer_model: str,
    prompt_version: str,
) -> GenerationScoreRecord:
    """判一条回答的引用是否越界，并落成逐题记录。

    越界引用只记**重拼出来的标记**，不从答案里切片——理由见 `GenerationScoreRecord`。
    去重保序：记的是「引了哪些越界的章」，不是「越界了几次」。
    """
    hits = find_citations(answer.text)
    allowed = set(answer.chapters)

    seen: dict[str, None] = {}
    for hit in hits:
        if hit.chapter_index not in allowed:
            seen[f"[C{hit.chapter_index}]"] = None

    return GenerationScoreRecord(
        question_id=str(question["id"]),
        question_type=str(question["type"]),
        difficulty=str(question["difficulty"]),
        expect_refusal=bool(question["expect_refusal"]),
        status=answer.status,
        citation_count=len(hits),
        citation_in_set=not seen,
        citation_out_of_range=tuple(seen),
        citation_malformed_count=len(find_violations(answer.text)),
        request_id=answer.request_id,
        answer_provider=answer_provider,
        answer_model=answer_model,
        prompt_version=prompt_version,
    )


def aggregate_generation(records: Sequence[GenerationScoreRecord]) -> dict[str, object]:
    """汇总成 `summary.json` 的 `generation` 一节：总体 + 按题型 / 难度分列。

    **失败的题留在拒答的分母里**，不让分母随结果塌缩：一次 provider 抖动就让
    `refusal_correct` 掉下来，正是想要的——带故障的 run 本来就该重跑而不是被评分。
    引用那一项相反，它的分母只含真答出来的题，理由见模块 docstring。
    """
    scored = list(records)
    answered = [r for r in scored if r.status == STATUS_ANSWERED]
    expected_refusals = [r for r in scored if r.expect_refusal]
    expected_answers = [r for r in scored if not r.expect_refusal]

    return {
        "question_count": len(scored),
        "generation_failed": sum(
            1 for r in scored if r.status == STATUS_GENERATION_FAILED
        ),
        "answered": len(answered),
        "citation_in_set": _ratio(
            sum(1 for r in answered if r.citation_in_set), len(answered)
        ),
        "citation_in_set_denominator": len(answered),
        # 空集天然满足集合判定，所以「一条引用都没标」必须单列——
        # 否则一个从不标注引用的回答会带着 `citation_in_set = 1.0` 通过。
        "answered_without_citation": sum(1 for r in answered if r.citation_count == 0),
        "citation_out_of_range_total": sum(len(r.citation_out_of_range) for r in scored),
        "citation_malformed_total": sum(r.citation_malformed_count for r in scored),
        "refusal_correct": _ratio(
            sum(1 for r in expected_refusals if r.status in _REFUSAL_STATUSES),
            len(expected_refusals),
        ),
        "refusal_denominator": len(expected_refusals),
        # 反向错误单列：只报 `refusal_correct` 时，「见谁都拒答」的模型拿满分。
        "refusal_false_positive": sum(
            1 for r in expected_answers if r.status in _REFUSAL_STATUSES
        ),
        "per_type": _breakdown(scored, lambda r: r.question_type),
        "per_difficulty": _breakdown(scored, lambda r: r.difficulty),
    }


def _breakdown(
    records: Sequence[GenerationScoreRecord],
    key_of: Callable[[GenerationScoreRecord], str],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[GenerationScoreRecord]] = {}
    for record in records:
        grouped.setdefault(key_of(record), []).append(record)

    result: dict[str, dict[str, object]] = {}
    for key, items in sorted(grouped.items()):
        answered = [r for r in items if r.status == STATUS_ANSWERED]
        result[key] = {
            "questions": len(items),
            "answered": len(answered),
            "citation_in_set": _ratio(
                sum(1 for r in answered if r.citation_in_set), len(answered)
            ),
            "citation_in_set_denominator": len(answered),
            "generation_failed": sum(
                1 for r in items if r.status == STATUS_GENERATION_FAILED
            ),
        }
    return result


def generation_failure_rows(
    records: Sequence[GenerationScoreRecord],
) -> tuple[dict[str, object], ...]:
    """答案层的失败清单：只写指针与指标快照，**不写答案也不写素材**。

    进 `failures.md` 的三类：生成失败（要重跑）、引用越界（引用纪律出了问题）、
    该拒答却没拒答（`expect_refusal` 没兑现）。
    """
    rows: list[dict[str, object]] = []
    for record in records:
        if (
            record.status == STATUS_GENERATION_FAILED
            or record.citation_out_of_range
            or (record.expect_refusal and record.status not in _REFUSAL_STATUSES)
        ):
            rows.append(
                {
                    "question_id": record.question_id,
                    "stage": _failure_stage(record),
                    "chunk_key": "",
                    "metrics": (
                        f"status {record.status} citations {record.citation_count} "
                        f"out_of_range {len(record.citation_out_of_range)} "
                        f"malformed {record.citation_malformed_count} "
                        f"expect_refusal {record.expect_refusal}"
                    ),
                    "question_form": record.question_type,
                }
            )
    return tuple(rows)


def _failure_stage(record: GenerationScoreRecord) -> str:
    if record.status == STATUS_GENERATION_FAILED:
        return "generation"
    if record.citation_out_of_range:
        return "citation"
    return "refusal"


def _ratio(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


__all__ = [
    "AnswerOutcome",
    "aggregate_generation",
    "fold_answer",
    "generation_failure_rows",
    "score_answer",
]

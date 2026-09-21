"""生成层的**确定性**指标（M0-04 §5.2）。

这一层里能确定性算的只有引用相关的那几条——它们不调模型、不依赖 judge，所以
M0 阶段就能算、也就能当门禁。judge 那五条（`point_coverage` / `faithfulness` /
`answer_relevancy` / `answer_boundary_violation` / `citation_supported`）在校准
达到 Cohen's kappa ≥ 0.6 之前只报告、不作结论（M0-04 §6），本模块一概不碰。

**这条不变量贯穿全文件：任何写进记录的东西都不得是答案的切片。**
越界的引用只记标记本身（`[C45]`），而且是从解析出来的章号**重新拼**的；
非规范写法只记条数。原因是 `domain/citation.py` 的 `CANDIDATE_PATTERN` 里那个
`[^\\]]*`——它能一路吃到下一个 `]`，`find_violations` 返回的片段里可能裹着一整段正文。
`temp/run.gen.jsonl` 才是放原文的地方。
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from omniread.domain.citation import find_citations, find_violations
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_GENERATION_FAILED,
    GenerationScoreRecord,
)

#: 门禁用的键名：`answer_citation_membership`（M0-04 §6）
MEMBERSHIP_KEY = "answer_citation_membership"


@dataclass(frozen=True, slots=True)
class CitationVerdict:
    """一条回答的引用判定结果。字段全部是计数或重拼出来的短标记，不含正文。"""

    citation_count: int
    out_of_range: tuple[str, ...]
    malformed_count: int
    membership_ok: bool


def judge_citation_membership(
    answer_text: str | None,
    allowed_chapters: Collection[int],
    *,
    expect_refusal: bool,
) -> CitationVerdict:
    """判一条回答的引用是否合规（M0-04 §5.2 的两个条件）。

    - ① **全部**引用都在允许集合内（允许集合 = 当次 `context_chapters` 的章号集）；
    - ② **非拒答题至少有一条引用**。没有 ② 的话，一个从不标注引用的回答会满分通过
      ——集合判定的空集天然安全，门禁恒真等于没有门禁。

    `answer_text=None` 表示**这一题没有答案**（生成失败）。它一律判失败，包括拒答题：
    拒答题免的是条件 ②，不是免于「必须真的产出一条回答」。故障记成拒答题会让
    `refusal_correct` 与这条门禁同时失真。

    ② 只用 Golden 的 `expect_refusal`，不引入 judge——所以这条门禁在 M0 就是可判定的。
    """
    if answer_text is None:
        return CitationVerdict(0, (), 0, membership_ok=False)

    hits = find_citations(answer_text)
    allowed = set(allowed_chapters)

    # 去重保序：记的是「引了哪些越界的章」，不是「越界了几次」。
    seen: dict[str, None] = {}
    for hit in hits:
        if hit.chapter_index not in allowed:
            seen[f"[C{hit.chapter_index}]"] = None
    out_of_range = tuple(seen)

    return CitationVerdict(
        citation_count=len(hits),
        out_of_range=out_of_range,
        malformed_count=len(find_violations(answer_text)),
        membership_ok=not out_of_range and (expect_refusal or bool(hits)),
    )


def aggregate_generation(
    records: Sequence[GenerationScoreRecord],
) -> dict[str, object]:
    """生成层汇总。

    **失败的题留在分母里**，不让分母随结果塌缩——「分母随映射结果塌缩会让指标偏高」
    是映射侧就定下的口径（M0-02 §6.2）。代价是一次 provider 抖动就会让门禁红：
    那正是想要的，一次带故障的 run 本来就该重跑而不是被评分。失败条数在
    `generation_failed` 里单列，不和「答错了」混在一起。

    judge 那五条指标在当前阶段全是 `None`（未执行）。全为 `None` 时**不给**汇总值，
    而不是给 `0.0`——「还没跑」与「跑了全零」在产物里必须能分开。
    """
    scored = list(records)
    total = len(scored)
    judge_keys = (
        "point_coverage",
        "faithfulness",
        "answer_relevancy",
        "answer_boundary_violation",
        "citation_supported",
    )

    summary: dict[str, object] = {
        "question_count": total,
        MEMBERSHIP_KEY: _ratio(
            sum(1 for r in scored if r.citation_membership_ok), total
        ),
        # 分母单列，理由同检索层：不写出来就没法判断两次 run 是否同分母。
        # 这里恒等于题数（失败的题不剔除），列出来正是为了让人一眼看出它没缩水。
        "citation_membership_denominator": total,
        "generation_failed": sum(1 for r in scored if r.status == STATUS_GENERATION_FAILED),
        "citation_out_of_range_total": sum(len(r.citation_out_of_range) for r in scored),
        "citation_malformed_total": sum(r.citation_malformed_count for r in scored),
        "answered": sum(1 for r in scored if r.status == STATUS_ANSWERED),
    }
    for key in judge_keys:
        values = [getattr(r, key) for r in scored]
        present = [v for v in values if v is not None]
        # 只有全部题都算出来了才给汇总；部分缺失时给 None，免得半份数据的均值冒充全量。
        summary[key] = (
            sum(present) / len(present) if present and len(present) == total else None
        )

    summary["per_type"] = _breakdown(scored, lambda r: r.question_type)
    summary["per_difficulty"] = _breakdown(scored, lambda r: r.difficulty)
    return summary


def _breakdown(
    records: Sequence[GenerationScoreRecord],
    key_of: Callable[[GenerationScoreRecord], str],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[GenerationScoreRecord]] = {}
    for record in records:
        grouped.setdefault(key_of(record), []).append(record)

    result: dict[str, dict[str, object]] = {}
    for key, items in sorted(grouped.items()):
        result[key] = {
            "questions": len(items),
            "citation_membership_denominator": len(items),
            MEMBERSHIP_KEY: _ratio(
                sum(1 for r in items if r.citation_membership_ok), len(items)
            ),
            "generation_failed": sum(
                1 for r in items if r.status == STATUS_GENERATION_FAILED
            ),
        }
    return result


def _ratio(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


__all__ = [
    "MEMBERSHIP_KEY",
    "CitationVerdict",
    "aggregate_generation",
    "judge_citation_membership",
]

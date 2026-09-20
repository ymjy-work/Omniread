"""检索层指标（M0-04 §5.1）—— 全部确定性，不含任何模型判断。

口径先定死再谈数字，否则同一个分数换个分母就能得出相反结论（`M0-04` §5.1 原话）。
这里定死三条：

1. **命中判定以 `assembled` 为准**（M0-04 §5.1）：只有真正进入 prompt 的段算命中。
   逐阶段列表另报作诊断——「dense 召回了但被装配截掉」与「根本没召回」是两回事。
2. **分母含未映射的 evidence**：`evidence_recall` 的分母是该题全部 evidence，
   不是「映射成功的那些」。分母随映射结果塌缩会让指标偏高且不可比
   （`M0-02` §6.2 的原话）。
3. **`leak` 逐阶段都算**，任一阶段 >0 即红（`M0-02` §8.7）。只看 assembled 会漏掉
   「召回了越界内容但被装配丢掉」——那仍是检索链的泄漏，只是没进 prompt。

`evidence_recall` / `group_recall` / `all_evidence_recall` 三者的确切定义规格未给
（只列了名字与归类），本模块的取值是**实现时定的**，与 `must_cite_recall` 的区别是：

| 指标 | 层次 | 组内 |
| --- | --- | --- |
| `group_recall` | 组 | OR |
| `evidence_recall` | 单条 evidence | 不分组 |
| `all_evidence_recall` | 题 | **AND**（组内也要全中，最严口径） |
| `must_cite_recall` | 题 | OR（组间 AND）—— 规格已定义 |
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from omniread.domain.text import evidence_hash
from omniread.pipelines.evaluation.types import RetrievalScoreRecord
from omniread.pipelines.mapping.artifacts import MappingRecord
from omniread.pipelines.mapping.types import MATCH_MATCHED
from omniread.pipelines.retrieval.types import RetrievalOutcome

# realm 等级：只有 past 才有越界一说。
_REALM_PAST = "past"

_STAGE_FIELDS = {
    "dense": ("dense", "leak_dense", "dense_keys"),
    "kw": ("kw", "leak_kw", "kw_keys"),
    "fused": ("fused", "leak_fused", "fused_keys"),
    "rerank": ("reranked", "leak_rerank", "rerank_keys"),
    "assembled": ("assembled", "leak_assembled", "assembled_keys"),
}


def chapter_index_of(chapter_id: str) -> int:
    """`book:1:chapter:N` → N；取不到即抛错，不静默当 0。"""
    tail = chapter_id.rsplit(":", 1)[-1]
    if not tail.isdigit():
        raise ValueError(f"chapter_id 形如 book:1:chapter:N，收到 {chapter_id!r}")
    return int(tail)


def score_question(
    question: Mapping[str, Any],
    outcome: RetrievalOutcome,
    mapping_lookup: Mapping[str, str | None],
) -> RetrievalScoreRecord:
    """把一次检索结果按该题的 `must_cite_groups` 打分。

    `mapping_lookup` 是 `evidence_hash -> matched_chunk_key`；值为 None 表示该条
    evidence 未映射上（`unmatched` / `low_conf`），它仍进分母。
    """
    groups: list[list[dict[str, str]]] = list(question["must_cite_groups"])
    assembled_keys = {chunk.chunk_key for chunk in outcome.assembled}
    assembled_chapters = {chunk.chapter_index for chunk in outcome.assembled}

    groups_hit = 0
    evidence_total = 0
    evidence_hit = 0
    evidence_mapped = 0
    # 最严口径：每一条 evidence 都得命中（组内也取 AND）。与 `must_cite_hit`
    # （组内 OR）是两回事，两者都报才能看出「组内靠一条撑住」的比例。
    every_evidence_hit = True
    mapped_keys: set[str] = set()

    for group in groups:
        group_hit = False
        for evidence in group:
            evidence_total += 1
            key = mapping_lookup.get(
                evidence_hash(evidence["chapter_id"], evidence["content"])
            )
            if key is None:
                every_evidence_hit = False
                continue
            evidence_mapped += 1
            mapped_keys.add(key)
            if key in assembled_keys:
                group_hit = True
                evidence_hit += 1
            else:
                every_evidence_hit = False
        if group_hit:
            groups_hit += 1

    chapter_hit = all(
        chapter_index_of(evidence["chapter_id"]) in assembled_chapters
        for group in groups
        for evidence in group
    )

    progress = _progress_of(question)
    leaks = {
        field: _count_leaks(getattr(outcome, attribute), progress)
        for field, (attribute, _, _) in _STAGE_FIELDS.items()
    }

    return RetrievalScoreRecord(
        question_id=str(question["id"]),
        question_type=str(question["type"]),
        difficulty=str(question["difficulty"]),
        level=str(question["level"]),
        progress=progress,
        expect_refusal=bool(question["expect_refusal"]),
        must_cite_hit=groups_hit == len(groups) and len(groups) > 0,
        groups_total=len(groups),
        groups_hit=groups_hit,
        evidence_total=evidence_total,
        evidence_hit=evidence_hit,
        evidence_mapped=evidence_mapped,
        all_evidence_hit=every_evidence_hit and evidence_total > 0,
        chapter_recall_hit=chapter_hit,
        leak_dense=leaks["dense"],
        leak_kw=leaks["kw"],
        leak_fused=leaks["fused"],
        leak_rerank=leaks["rerank"],
        leak_assembled=leaks["assembled"],
        dense_keys=tuple(hit.chunk_key for hit in outcome.dense),
        kw_keys=tuple(hit.chunk_key for hit in outcome.kw),
        fused_keys=tuple(hit.chunk_key for hit in outcome.fused),
        rerank_keys=tuple(hit.chunk_key for hit in outcome.reranked),
        assembled_keys=tuple(chunk.chunk_key for chunk in outcome.assembled),
        dropped=tuple(f"{item.reason}:{item.chunk_key}" for item in outcome.dropped),
        mapped_not_assembled_keys=tuple(sorted(mapped_keys - assembled_keys)),
    )


def _progress_of(question: Mapping[str, object]) -> int | None:
    if question["level"] != _REALM_PAST:
        return None
    progress = question.get("progress")
    if not isinstance(progress, int) or isinstance(progress, bool):
        raise ValueError(f"{question['id']}: level=past 必须有整数 progress")
    return progress


def _count_leaks(hits: Sequence[object], progress: int | None) -> int:
    if progress is None:
        return 0
    return sum(1 for hit in hits if getattr(hit, "chapter_index", 0) > progress)


def aggregate(records: Sequence[RetrievalScoreRecord]) -> dict[str, object]:
    """汇总成 `summary.json` 的口径：总体 + 按类型分列 + 按难度分列。

    **只分列、不加权**：难度是评测者给的主观标签，权重会把它乘进被测系统的分数，
    改一个标签就悄悄挪动总分。分列既能看到「难题差在哪」，又不会让标签动了带走头条数字。
    """
    scored = list(records)
    population = _must_cite_population(scored)
    return {
        "question_count": len(scored),
        "must_cite_recall": _ratio(
            sum(1 for r in population if r.must_cite_hit), len(population)
        ),
        # 分母单列出来：它是口径的一部分，不列出来就没法判断两次 run 是否同分母。
        "must_cite_recall_denominator": len(population),
        "evidence_recall": _ratio(
            sum(r.evidence_hit for r in scored), sum(r.evidence_total for r in scored)
        ),
        "group_recall": _ratio(
            sum(r.groups_hit for r in scored), sum(r.groups_total for r in scored)
        ),
        "all_evidence_recall": _ratio(
            sum(1 for r in scored if r.all_evidence_hit), len(scored)
        ),
        "chapter_recall": _ratio(
            sum(1 for r in scored if r.chapter_recall_hit), len(scored)
        ),
        "evidence_mapped": _ratio(
            sum(r.evidence_mapped for r in scored), sum(r.evidence_total for r in scored)
        ),
        # 硬门禁：任一题任一阶段 >0 即不为 0。
        "leak": sum(r.leak_total for r in scored),
        "per_type": _breakdown(scored, lambda r: r.question_type),
        "per_difficulty": _breakdown(scored, lambda r: r.difficulty),
        "per_level": _breakdown(scored, lambda r: r.level),
    }


def _must_cite_population(
    records: Sequence[RetrievalScoreRecord],
) -> list[RetrievalScoreRecord]:
    """`must_cite_recall` 的分母人群：`must_cite_groups` 非空且不是拒答题。

    **分子分母必须取同一批题**。曾在分子上漏掉「排除拒答」这一步，比率于是能跑到
    1 以上——那是最容易在评审里被一眼看穿、又最容易在实现里漏掉的一类错。
    `must_cite_groups` 为空是 schema 非法（M0-04 §5.1），这里的 `groups_total > 0`
    只是防御，不是判定。
    """
    return [r for r in records if r.groups_total > 0 and not r.expect_refusal]


def _breakdown(
    records: Sequence[RetrievalScoreRecord],
    key_of: Callable[[RetrievalScoreRecord], str],
) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[RetrievalScoreRecord]] = {}
    for record in records:
        grouped.setdefault(key_of(record), []).append(record)

    result: dict[str, dict[str, float | int]] = {}
    for key, items in sorted(grouped.items()):
        population = _must_cite_population(items)
        result[key] = {
            "questions": len(items),
            # 分列走与总口径同一个分母人群，否则「各档加起来」对不上总数。
            "must_cite_recall": _ratio(
                sum(1 for r in population if r.must_cite_hit), len(population)
            ),
            "evidence_recall": _ratio(
                sum(r.evidence_hit for r in items), sum(r.evidence_total for r in items)
            ),
            "leak": sum(r.leak_total for r in items),
        }
    return result


def _ratio(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


def matched_keys_from_records(
    records: Sequence[MappingRecord],
) -> dict[str, str | None]:
    """把映射产物折成 `evidence_hash -> matched_chunk_key` 的查表。

    只认 `MATCH_MATCHED`：`low_conf` 的 `matched_chunk_key` 虽然不是 NULL，
    但它表示「没有块完整包含该证据」，拿它当命中会让指标虚高。
    """
    return {
        record.evidence_hash: (
            record.matched_chunk_key if record.match_status == MATCH_MATCHED else None
        )
        for record in records
    }


def summarize_counts(records: Sequence[RetrievalScoreRecord]) -> dict[str, int]:
    """失败定位用的小计数：哪一档判据、哪一类失败各有多少。"""
    counts: Counter[str] = Counter()
    for record in records:
        if not record.must_cite_hit:
            counts["must_cite_miss"] += 1
        if record.evidence_mapped < record.evidence_total:
            counts["evidence_unmapped"] += 1
        if record.mapped_not_assembled_keys:
            counts["mapped_but_dropped"] += 1
        if record.leak_total:
            counts["leaked"] += 1
    return dict(sorted(counts.items()))

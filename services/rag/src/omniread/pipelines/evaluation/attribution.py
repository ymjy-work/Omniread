"""未命中 evidence 的逐条归因（M1-1 步骤 1）。

**它比 summary / failures 多要两路输入，这不是疏漏。** 那两者是
`retrieval.scores.jsonl` 的确定性函数（所以能离线零费用重算）；归因做不到，因为
逐题记录里只有**去重后的 chunk_key 集合**，而一条 key 可能承多条 evidence
（同一段原文被多道题复用）：本 baseline 是 107 条 evidence 落在 73 个唯一 key 上。
要按 evidence 计数（那才是与 `evidence_recall` 同一把尺子的单位），就必须拿回
Golden 的 evidence 列表与 evidence_hash → chunk_key 的映射。

**口径由一道闸门保证，而不是靠注释**：每题算出的 `assembled` 条数必须等于记录里的
`evidence_hit`，丢失条数必须等于 `evidence_total - evidence_hit`。两处一旦分叉就抛错，
不静默出一份与头条数字对不上的报告。所以改 `metrics.py` 的命中规则会立刻在这里炸出来。

阶段划分（一条 evidence 的 key 最后一次出现在哪一阶段）：

- `rerank`：进过重排，被装配裁掉 —— 修法是 `ask_top_k` / `ask_max_chapters` /
  `ask_chunks_per_chapter`；
- `fused`：进过融合，被 `rerank_k` 截掉 —— 修法是重排窗口；
- `fused_truncated`：至少在某个召回通道里出现过、没进融合 —— 修法是融合段数；
- `channel_missed`：两个召回通道都没返回 —— 修法是候选深度 `dense_k` / `kw_k`；
- `unmapped`：压根没映射上 —— 属 Golden 或映射问题，不是检索问题。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from omniread.domain.text import evidence_hash
from omniread.pipelines.evaluation.types import RetrievalScoreRecord

STAGE_ASSEMBLED = "assembled"
STAGE_RERANK = "rerank"
STAGE_FUSED = "fused"
STAGE_FUSED_TRUNCATED = "fused_truncated"
STAGE_CHANNEL_MISSED = "channel_missed"
STAGE_UNMAPPED = "unmapped"

#: 未命中的阶段，顺序即「越靠前越晚丢失」，渲染按它排。
LOSS_STAGES = (
    STAGE_RERANK,
    STAGE_FUSED,
    STAGE_FUSED_TRUNCATED,
    STAGE_CHANNEL_MISSED,
    STAGE_UNMAPPED,
)


class AttributionError(ValueError):
    """归因结果与逐题记录对不上——口径分叉了，不出一份看着合理的报告。"""


@dataclass(frozen=True, slots=True)
class StageSets:
    """一道题的各阶段 chunk_key 集合，一次建好反复查。"""

    assembled: frozenset[str]
    rerank: frozenset[str]
    fused: frozenset[str]
    channels: frozenset[str]


def stage_sets(record: RetrievalScoreRecord) -> StageSets:
    return StageSets(
        assembled=frozenset(record.assembled_keys),
        rerank=frozenset(record.rerank_keys),
        fused=frozenset(record.fused_keys),
        channels=frozenset(record.dense_keys) | frozenset(record.kw_keys),
    )


def classify_evidence(key: str | None, sets: StageSets) -> str:
    """一条 evidence 的丢失阶段；`assembled` 即命中。"""
    if key is None:
        return STAGE_UNMAPPED
    if key in sets.assembled:
        return STAGE_ASSEMBLED
    if key in sets.rerank:
        return STAGE_RERANK
    if key in sets.fused:
        return STAGE_FUSED
    if key in sets.channels:
        return STAGE_FUSED_TRUNCATED
    return STAGE_CHANNEL_MISSED


@dataclass(frozen=True, slots=True)
class LossAttribution:
    """全量结果。`by_stage` 与 `by_type_stage` 的单位都是 **evidence 条数**。"""

    #: 全部题目合计。
    by_stage: Mapping[str, int]
    #: 题型 → 该题型的 evidence 总数。
    by_type_total: Mapping[str, int]
    #: 题型 → 阶段 → 条数。
    by_type_stage: Mapping[str, Mapping[str, int]]
    #: 题型 → 阶段 → 去重后的 chunk_key 数（与 `M0-进度与交接.md` §3 的 41/19/13 同单位）。
    by_type_unique_keys: Mapping[str, Mapping[str, int]]

    @property
    def evidence_total(self) -> int:
        return sum(self.by_type_total.values())

    @property
    def hit(self) -> int:
        return self.by_stage.get(STAGE_ASSEMBLED, 0)

    @property
    def missed(self) -> int:
        return sum(self.by_stage.get(stage, 0) for stage in LOSS_STAGES)

    @property
    def unique_keys_missed(self) -> int:
        return sum(
            counts.get(stage, 0)
            for counts in self.by_type_unique_keys.values()
            for stage in LOSS_STAGES
        )


def attribute_losses(
    questions: Sequence[Mapping[str, Any]],
    mapping_lookup: Mapping[str, str | None],
    records: Sequence[RetrievalScoreRecord],
) -> LossAttribution:
    """逐条归因，并按题型聚合。题目顺序不影响结果。"""
    by_id = {record.question_id: record for record in records}

    by_stage: Counter[str] = Counter()
    by_type_total: Counter[str] = Counter()
    by_type_stage: dict[str, Counter[str]] = {}
    by_type_keys: dict[str, dict[str, set[str]]] = {}

    for question in questions:
        question_id = str(question["id"])
        record = by_id.get(question_id)
        if record is None:
            raise AttributionError(f"逐题记录里没有 {question_id}——题目与记录不是同一批")
        question_type = str(question["type"])
        sets = stage_sets(record)

        counts: Counter[str] = Counter()
        keys: dict[str, set[str]] = {}
        for group in question["must_cite_groups"]:
            for evidence in group:
                key = mapping_lookup.get(evidence_hash(evidence["chapter_id"], evidence["content"]))
                stage = classify_evidence(key, sets)
                counts[stage] += 1
                if key is not None and stage != STAGE_ASSEMBLED:
                    keys.setdefault(stage, set()).add(key)

        # 闸门：归因必须与逐题记录里的命中数逐题对上。对不上说明两处口径已经分叉。
        if counts[STAGE_ASSEMBLED] != record.evidence_hit:
            raise AttributionError(
                f"{question_id}: 归因算出命中 {counts[STAGE_ASSEMBLED]} 条，"
                f"记录里 evidence_hit={record.evidence_hit}——命中规则分叉了"
            )
        expected_missed = record.evidence_total - record.evidence_hit
        missed = sum(counts[stage] for stage in LOSS_STAGES)
        if missed != expected_missed:
            raise AttributionError(
                f"{question_id}: 归因算出丢失 {missed} 条，"
                f"记录里 evidence_total - evidence_hit={expected_missed}——阶段划分漏了分支"
            )

        by_stage.update(counts)
        by_type_total[question_type] += record.evidence_total
        by_type_stage.setdefault(question_type, Counter()).update(counts)
        bucket = by_type_keys.setdefault(question_type, {})
        for stage, stage_keys in keys.items():
            bucket.setdefault(stage, set()).update(stage_keys)

    return LossAttribution(
        by_stage=dict(by_stage),
        by_type_total=dict(by_type_total),
        by_type_stage={key: dict(value) for key, value in by_type_stage.items()},
        by_type_unique_keys={
            key: {stage: len(stage_keys) for stage, stage_keys in value.items()}
            for key, value in by_type_keys.items()
        },
    )


def render_attribution(attribution: LossAttribution, *, run_id: str) -> str:
    """渲染成 markdown。**只写指针与计数**，与 run 产物同一红线。"""
    lines: list[str] = []
    lines.append(f"# 未命中 evidence 归因（run `{run_id}`）")
    lines.append("")
    lines.append(
        f"evidence 合计 {attribution.evidence_total} 条："
        f"命中 {attribution.hit} 条、未命中 {attribution.missed} 条，"
        f"落在 {attribution.unique_keys_missed} 个唯一 chunk_key 上。"
    )
    lines.append("")
    lines.append("> 两个数不同不是矛盾：同一段原文被多道题复用，一条 chunk_key 承多条 evidence。")
    lines.append("> 与 `evidence_recall` 同单位的是**条数**那一列。")
    lines.append("")

    lines.append("## 按丢失阶段（单位：条 evidence）")
    lines.append("")
    lines.append("| 丢失阶段 | 条数 | 占未命中 | 对应的修法 |")
    lines.append("| --- | --- | --- | --- |")
    fixes = {
        STAGE_RERANK: "装配 cap（`ask_top_k` / `ask_max_chapters` / `ask_chunks_per_chapter`）",
        STAGE_FUSED: "重排窗口（`rerank_k`）",
        STAGE_FUSED_TRUNCATED: "融合段数（`rrf_k`）",
        STAGE_CHANNEL_MISSED: "候选深度（`dense_k` / `kw_k`）",
        STAGE_UNMAPPED: "映射或 Golden，不是检索",
    }
    missed = attribution.missed or 1
    for stage in LOSS_STAGES:
        count = attribution.by_stage.get(stage, 0)
        if count:
            lines.append(f"| `{stage}` | {count} | {count / missed:.1%} | {fixes[stage]} |")
    lines.append("")

    lines.append("## 按题型")
    lines.append("")
    header = "| 题型 | evidence | 未命中 | 召回率 |"
    for stage in LOSS_STAGES:
        header += f" {stage} |"
    lines.append(header)
    lines.append("| --- | --- | --- | --- |" + " --- |" * len(LOSS_STAGES))
    for question_type in sorted(attribution.by_type_total):
        total = attribution.by_type_total[question_type]
        counts = attribution.by_type_stage.get(question_type, {})
        hit = counts.get(STAGE_ASSEMBLED, 0)
        type_missed = sum(counts.get(stage, 0) for stage in LOSS_STAGES)
        recall = hit / total if total else 0.0
        row = f"| `{question_type}` | {total} | {type_missed} | {recall:.4f} |"
        for stage in LOSS_STAGES:
            row += f" {counts.get(stage, 0)} |"
        lines.append(row)
    lines.append("")

    lines.append("## 按题型的唯一 chunk_key 数（对比 evidence 条数）")
    lines.append("")
    lines.append("| 题型 | 未命中 key 数 |")
    lines.append("| --- | --- |")
    for question_type in sorted(attribution.by_type_unique_keys):
        bucket = attribution.by_type_unique_keys[question_type]
        lines.append(f"| `{question_type}` | {sum(bucket.values())} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "LOSS_STAGES",
    "STAGE_ASSEMBLED",
    "STAGE_CHANNEL_MISSED",
    "STAGE_FUSED",
    "STAGE_FUSED_TRUNCATED",
    "STAGE_RERANK",
    "STAGE_UNMAPPED",
    "AttributionError",
    "LossAttribution",
    "StageSets",
    "attribute_losses",
    "classify_evidence",
    "render_attribution",
    "stage_sets",
]

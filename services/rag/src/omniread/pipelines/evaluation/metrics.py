"""检索层指标（M0-04 §5.1）—— 全部确定性，不含任何模型判断。

只报两个数：

- **`evidence_recall`**：进入 `assembled` 的证据条数 ÷ 该题全部证据条数。
  命中判定以 `assembled` 为准（`M0-04` §5.1）：只有真正进入 prompt 的段算命中；
  逐阶段指针另存作诊断——「召回了但被装配截掉」与「根本没召回」是两回事，
  而这两件事的修法完全不同。分母是**该题全部 evidence**，不是「映射成功的那些」：
  分母随映射结果塌缩会让指标偏高且不可比（`M0-02` §6.2）。
  `evidence_mapped` 单列——它衡量的是**映射**而不是检索，混进同一个数会让
  「文本切片没对上」与「检索没召回到」分不开。

- **`leak`**：召回结果里越界章节的数量，**硬门禁**，任一阶段 >0 即红（`M0-02` §8.7）。
  只看 `assembled` 会漏掉「召回了越界内容但被装配丢掉」——那仍是检索链的泄漏，
  只是没进 prompt。

口径先定死再谈数字：同一个分数换个分母就能得出相反结论（`M0-04` §5.1 原话）。
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

#: 阶段名 → (`RetrievalOutcome` 上的结果集属性, 记录上的 leak 计数列)。
#: 逐阶段的 `*_keys` 指针在 `score_question` 里直接取，不经过这张表——
#: 它只服务「哪个阶段的越界最多」这一件事。
_STAGE_FIELDS = {
    "dense": ("dense", "leak_dense"),
    "kw": ("kw", "leak_kw"),
    "fused": ("fused", "leak_fused"),
    "rerank": ("reranked", "leak_rerank"),
    "assembled": ("assembled", "leak_assembled"),
}


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

    evidence_total = 0
    evidence_hit = 0
    evidence_mapped = 0
    mapped_keys: set[str] = set()

    for group in groups:
        for evidence in group:
            evidence_total += 1
            key = mapping_lookup.get(
                evidence_hash(evidence["chapter_id"], evidence["content"])
            )
            if key is None:
                continue
            evidence_mapped += 1
            mapped_keys.add(key)
            if key in assembled_keys:
                evidence_hit += 1

    progress = _progress_of(question)
    leaks = {
        field: _count_leaks(getattr(outcome, attribute), progress)
        for field, (attribute, _) in _STAGE_FIELDS.items()
    }

    return RetrievalScoreRecord(
        question_id=str(question["id"]),
        question_type=str(question["type"]),
        difficulty=str(question["difficulty"]),
        level=str(question["level"]),
        progress=progress,
        expect_refusal=bool(question["expect_refusal"]),
        evidence_total=evidence_total,
        evidence_hit=evidence_hit,
        evidence_mapped=evidence_mapped,
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
    """汇总成 `summary.json` 的口径：总体 + 按题型 / 难度 / realm 分列。

    **只分列、不加权**：难度是评测者给的主观标签，权重会把它乘进被测系统的分数，
    改一个标签就悄悄挪动总分。分列既能看到「难题差在哪」，又不会让标签动了带走头条数字。
    """
    scored = list(records)
    return {
        "question_count": len(scored),
        "evidence_recall": _ratio(
            sum(r.evidence_hit for r in scored), sum(r.evidence_total for r in scored)
        ),
        # 分母单列出来：它是口径的一部分，不列出来就没法判断两次 run 是否同分母，
        # 也没法把它与 `evidence_mapped` 分开读——那个量衡量的是**映射**，不是检索。
        "evidence_total": sum(r.evidence_total for r in scored),
        "evidence_mapped": _ratio(
            sum(r.evidence_mapped for r in scored), sum(r.evidence_total for r in scored)
        ),
        # 硬门禁：任一题任一阶段 >0 即不为 0。
        "leak": sum(r.leak_total for r in scored),
        "per_type": _breakdown(scored, lambda r: r.question_type),
        "per_difficulty": _breakdown(scored, lambda r: r.difficulty),
        "per_level": _breakdown(scored, lambda r: r.level),
    }


def _breakdown(
    records: Sequence[RetrievalScoreRecord],
    key_of: Callable[[RetrievalScoreRecord], str],
) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[RetrievalScoreRecord]] = {}
    for record in records:
        grouped.setdefault(key_of(record), []).append(record)

    result: dict[str, dict[str, float | int]] = {}
    for key, items in sorted(grouped.items()):
        result[key] = {
            "questions": len(items),
            # 分母与比率并排给出，理由同总口径：不列分母就没法判断两次 run 是否同分母。
            "evidence_total": sum(r.evidence_total for r in items),
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
    """失败定位用的小计数：证据在哪一环掉了。

    三档各自指向一种修法——`evidence_unmapped` 是文本切片的问题，
    `mapped_but_dropped` 是装配 cap 的问题，`leaked` 是 realm 过滤的问题。

    **三档不互斥**，一道题可能同时占两档（既有没有映射上的证据、又有映射上却被裁掉的），
    所以三个数相加**不等于**失败题数。要看「几道题失败」用 `failure_rows` 的长度。
    """
    counts: Counter[str] = Counter()
    for record in records:
        if record.evidence_mapped < record.evidence_total:
            counts["evidence_unmapped"] += 1
        if record.mapped_not_assembled_keys:
            counts["mapped_but_dropped"] += 1
        if record.leak_total:
            counts["leaked"] += 1
    return dict(sorted(counts.items()))

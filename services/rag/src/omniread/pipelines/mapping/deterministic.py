"""确定性 evidence→chunk 映射：章内区间包含。

Golden 的 evidence 按 `M0-04` §2.2 必须是**原文片段**；实测 357/357 都是所属章节正文的
精确子串。既然 evidence 是原文，覆盖它的 chunk 就由区间包含**精确给出**——不需要模型判断，
也就没有模型判断的误差。模型只在 evidence 不是精确子串时兜底（见 `fallback.py`）。

多块覆盖的处理：chunk i 以 chunk i-1 的尾 overlap 开头，所以跨边界的一段文本会同时落在
两个 chunk 里。两者都完整包含它，按「覆盖率最高」无法区分。真正的判别特征是**谁引入了这段
文本**——引入者把它放在自己的新增正文里，另一个只是把它放进了自己的 overlap 前缀。
实测 19/19 条多覆盖都能由这条唯一确定。

同一段证据在章内重复出现时，**逐个出现位置都算**：只看第一次出现会给出片面答案，
而重复段落在这本语料里并不罕见（同一句在一章内出现多次）。多个位置各落在不同 chunk 时，
如实记主次并写进理由，不装作只有一个归属。

`confidence` 恒为 1.0：区间包含是精确判据，没有「大概对」的中间态。可信度的差异由
`decision_tier` 承载（诊断用），不塞进 confidence——把确定的事实说成 0.9 分可信是失真。
"""

from __future__ import annotations

from collections.abc import Sequence

from omniread.domain.text import normalize_minimal
from omniread.pipelines.mapping.types import (
    DETERMINISTIC_MAPPER_MODEL,
    MATCH_LOW_CONF,
    MATCH_MATCHED,
    MATCH_UNMATCHED,
    ChunkSpan,
    MappingOutcome,
)

TIER_UNIQUE_COVER = "unique_cover"
TIER_INTRODUCER = "introducer"
TIER_MAX_COVERAGE = "max_coverage"
TIER_PARTIAL = "partial_overlap"
TIER_NONE = "no_overlap"
# 内部用：同一次出现里的「备块」。它参与候选排序，但永远不会成为某条结果的 decision_tier。
TIER_ALTERNATE = "alternate"


def map_evidence_deterministic(
    text: str,
    content: str,
    spans: Sequence[ChunkSpan],
    *,
    evidence_hash: str,
    chapter_id: str,
    mapper_prompt_version: str,
    mapper_model: str = DETERMINISTIC_MAPPER_MODEL,
) -> MappingOutcome:
    """把一条 evidence 映射到 chunk；不命中时如实返回 unmatched / low_conf。

    本函数只做确定性判定，不调用任何 provider。调用方在 `match_status` 不是 `matched`
    且配置了 mapper provider 时，才把这条交给兜底路径。
    """
    normalized = normalize_minimal(content)
    starts = _find_all(text, normalized)

    if not starts:
        return _outcome(
            evidence_hash=evidence_hash,
            chapter_id=chapter_id,
            status=MATCH_UNMATCHED,
            chunk_key=None,
            reason="evidence 不是本章正文的精确子串（本章内未找到）",
            alternative=None,
            tier=TIER_NONE,
            mapper_model=mapper_model,
            mapper_prompt_version=mapper_prompt_version,
        )

    length = len(normalized)
    candidates: list[tuple[ChunkSpan, str]] = []
    for start in starts:
        primary, alternative, tier = _locate(spans, start, start + length)
        if primary is not None:
            candidates.append((primary, tier))
        if alternative is not None:
            candidates.append((alternative, TIER_ALTERNATE))

    if candidates:
        chosen, tier = _pick_primary(candidates)
        distinct = {chunk.chunk_key for chunk, _ in candidates}
        others = sorted(
            (chunk for chunk, _ in candidates if chunk.chunk_key != chosen.chunk_key),
            key=lambda span: span.chunk_index,
        )
        alternative = others[0] if others else None
        reason = (
            f"精确子串在章内出现 {len(starts)} 次，"
            f"{len(distinct)} 个 chunk 完整包含，按 {tier} 定主次"
            + (f"，另有 {len(distinct) - 1} 个候选" if len(distinct) > 1 else "")
        )
        return _outcome(
            evidence_hash=evidence_hash,
            chapter_id=chapter_id,
            status=MATCH_MATCHED,
            chunk_key=chosen.chunk_key,
            reason=reason,
            # 契约只留一个 alternative；候选多于两个时多余的记在 reason 里，不静默丢弃。
            alternative=alternative.chunk_key if alternative else None,
            tier=tier,
            mapper_model=mapper_model,
            mapper_prompt_version=mapper_prompt_version,
        )

    # 没有任何块完整包含：退到部分覆盖，如实记 low_conf，不冒充命中。
    best, covered = _best_partial(spans, starts, length)
    if best is not None:
        return _outcome(
            evidence_hash=evidence_hash,
            chapter_id=chapter_id,
            status=MATCH_LOW_CONF,
            chunk_key=best.chunk_key,
            reason=(
                f"精确子串在章内出现 {len(starts)} 次，"
                f"但没有任何 chunk 完整包含；最佳者 {best.chunk_key} "
                f"仅覆盖 {covered}/{length} 字符"
            ),
            alternative=None,
            tier=TIER_PARTIAL,
            mapper_model=mapper_model,
            mapper_prompt_version=mapper_prompt_version,
        )

    return _outcome(
        evidence_hash=evidence_hash,
        chapter_id=chapter_id,
        status=MATCH_UNMATCHED,
        chunk_key=None,
        reason=f"精确子串在章内出现 {len(starts)} 次，但不与任何 chunk 区间重叠",
        alternative=None,
        tier=TIER_NONE,
        mapper_model=mapper_model,
        mapper_prompt_version=mapper_prompt_version,
    )


def _find_all(text: str, needle: str) -> list[int]:
    """`needle` 在 `text` 中的全部起始位置（升序、不重叠推进）。"""
    starts: list[int] = []
    at = text.find(needle)
    while at >= 0:
        starts.append(at)
        at = text.find(needle, at + 1)
    return starts


def _locate(
    spans: Sequence[ChunkSpan], start: int, end: int
) -> tuple[ChunkSpan | None, ChunkSpan | None, str]:
    """单次出现的判定：返回 (主块, 备块, 档位)；无完整包含时主块为 None。"""
    covering = [span for span in spans if span.start <= start and end <= span.end]
    if not covering:
        return None, None, TIER_NONE
    if len(covering) == 1:
        return covering[0], None, TIER_UNIQUE_COVER

    introducers = [span for span in covering if not _inside_overlap_prefix(span, start, end)]
    if len(introducers) == 1:
        primary = introducers[0]
        tier = TIER_INTRODUCER
    else:
        primary = max(covering, key=lambda span: (span.end - span.start, -span.start))
        tier = TIER_MAX_COVERAGE

    others = [span for span in covering if span.chunk_key != primary.chunk_key]
    alternative = (
        max(others, key=lambda span: (span.end - span.start, span.start)) if others else None
    )
    return primary, alternative, tier


def _pick_primary(candidates: Sequence[tuple[ChunkSpan, str]]) -> tuple[ChunkSpan, str]:
    """在多次出现的候选里定主块。

    唯一候选直接用；否则优先「引入者」——重复出现时每个位置各有一个引入者，
    多于一个即说明这段文本确实落在多处，退到按 chunk 序号取最早，保证同一输入同一结果。
    """
    by_key: dict[str, tuple[ChunkSpan, str]] = {}
    for span, tier in candidates:
        # 同一块被多次出现命中时保留更强的档位
        existing = by_key.get(span.chunk_key)
        if existing is None or _tier_rank(tier) < _tier_rank(existing[1]):
            by_key[span.chunk_key] = (span, tier)

    if len(by_key) == 1:
        return next(iter(by_key.values()))

    introducers = [item for item in by_key.values() if item[1] == TIER_INTRODUCER]
    if len(introducers) == 1:
        return introducers[0]

    best = min(by_key.values(), key=lambda item: item[0].chunk_index)
    return best[0], TIER_MAX_COVERAGE


def _tier_rank(tier: str) -> int:
    """档位强弱：唯一覆盖 > 引入者 > 兜底覆盖 > 仅作备选。数字越小越强。"""
    return {
        TIER_UNIQUE_COVER: 0,
        TIER_INTRODUCER: 1,
        TIER_MAX_COVERAGE: 2,
        TIER_ALTERNATE: 3,
    }.get(tier, 4)


def _best_partial(
    spans: Sequence[ChunkSpan], starts: Sequence[int], length: int
) -> tuple[ChunkSpan | None, int]:
    """所有出现位置里覆盖字符数最多的那个块。"""
    best: ChunkSpan | None = None
    best_covered = 0
    for start in starts:
        end = start + length
        for span in spans:
            covered = min(span.end, end) - max(span.start, start)
            if covered > best_covered:
                best, best_covered = span, covered
    return best, best_covered


def _inside_overlap_prefix(span: ChunkSpan, start: int, end: int) -> bool:
    """evidence 是否整段落在本块的 overlap 前缀里（即本块只是重复了上一块的内容）。"""
    return bool(span.overlap_len) and (end - span.start) <= span.overlap_len


def _outcome(
    *,
    evidence_hash: str,
    chapter_id: str,
    status: str,
    chunk_key: str | None,
    reason: str,
    alternative: str | None,
    tier: str,
    mapper_model: str,
    mapper_prompt_version: str,
) -> MappingOutcome:
    return MappingOutcome(
        evidence_hash=evidence_hash,
        chapter_id=chapter_id,
        match_status=status,
        matched_chunk_key=chunk_key,
        # 命中即 1.0（区间包含是精确判据）；未命中记 0，因为 confidence 列非空。
        confidence=1.0 if status == MATCH_MATCHED else 0.0,
        overlap_reason=reason,
        alternative_chunk_key=alternative,
        mapper_model=mapper_model,
        mapper_prompt_version=mapper_prompt_version,
        decision_tier=tier,
    )

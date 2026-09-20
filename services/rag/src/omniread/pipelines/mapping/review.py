"""人工抽样复核产物（M0-02 §6.4）：冷启动阶段 100% 复核，落 `temp/`。

**为什么落 `temp/` 而不是 `eval/runs/`**：复核要让人同时看到 evidence 与它命中的 chunk 正文，
chunk 正文是整段语料；`eval/` 进 git，红线不允许它出现在那里。这条规矩与
「回答原文只落 `temp/`」（M0-02 §7.1）是同一条。

冷启动要复核 357 条，逐条盲看不可行，所以产物按「复核成本」分层：绝大多数是
`unique_cover`（章内只有一个 chunk 完整包含该证据），复核者验的是**规则**不是逐条判断；
真正需要逐条看的只有跨块边界与章内重复出现的那几十条。

## 渲染上必须守住的一条

摘录**必须标出块边界**。相邻块天然重叠几十到上百字（`overlap_tokens=60`），
若只给「主块正文 ± N 字上下文」而不标边界，邻块的文字会混进来，
复核者会把**别的块的**内容读成「本块的上下文部分」，进而怀疑映射错了——
而错的其实是这份复核件的呈现。所以这里把块内与块外分块渲染，并给出每个
覆盖块内的 evidence 偏移，让「它是不是本块自己引入的」一眼可判。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from omniread.pipelines.mapping.artifacts import MappingRecord
from omniread.pipelines.mapping.deterministic import (
    TIER_INTRODUCER,
    TIER_MAX_COVERAGE,
    TIER_UNIQUE_COVER,
)
from omniread.pipelines.mapping.sources import ChapterSlices
from omniread.pipelines.mapping.types import MATCH_MATCHED

# 块外上下文：够看出「证据是不是跨过边界」即可。给太长会盖住邻块地界、制造误读。
_NEIGHBOUR_CONTEXT = 40
# 块内窗口：evidence 前后各留多少字。块本身最长约千字，全量展示会让复核件难读。
_INSIDE_WINDOW = 150


@dataclass(frozen=True, slots=True)
class CoverageView:
    """一个完整包含该 evidence 的块，以及它相对本块的位置。"""

    chunk_key: str
    start: int
    end: int
    overlap_len: int
    # evidence 在本块内的起始偏移；本块不含它时为空。
    offsets: tuple[int, ...]
    # 是否落在本块的**新增正文**里（即本块是引入者，而非重述上一块的尾部）。
    in_new_content: bool


@dataclass(frozen=True, slots=True)
class ReviewRow:
    question_id: str
    chapter_id: str
    evidence: str
    decision_tier: str
    match_status: str
    matched_chunk_key: str | None
    alternative_chunk_key: str | None
    overlap_reason: str
    # evidence 在整章内的全部出现位置。
    chapter_offsets: tuple[int, ...]
    coverages: tuple[CoverageView, ...]
    before_context: str
    inside_window: str
    after_context: str
    window_truncated_head: bool
    window_truncated_tail: bool


def build_review_rows(
    records: Sequence[MappingRecord],
    evidence: Sequence[object],
    slices: Mapping[str, ChapterSlices],
) -> list[ReviewRow]:
    """把映射结果与原文拼成可复核的行；`evidence` 与 `records` 同序一一对应。"""
    rows: list[ReviewRow] = []
    for record, item in zip(records, evidence, strict=True):
        content = item.content  # type: ignore[attr-defined]
        chapter = slices.get(record.chapter_id)
        if chapter is None:
            rows.append(_empty_row(record, content))
            continue
        rows.append(_build_row(record, content, chapter))
    return rows


def _build_row(record: MappingRecord, content: str, chapter: ChapterSlices) -> ReviewRow:
    from omniread.domain.text import normalize_minimal

    normalized = normalize_minimal(content)
    offsets: list[int] = []
    at = chapter.text.find(normalized)
    while at >= 0:
        offsets.append(at)
        at = chapter.text.find(normalized, at + 1)

    coverages: list[CoverageView] = []
    for span in chapter.spans:
        inside_offsets = [
            offset - span.start
            for offset in offsets
            if span.start <= offset and offset + len(normalized) <= span.end
        ]
        if not inside_offsets:
            continue
        coverages.append(
            CoverageView(
                chunk_key=span.chunk_key,
                start=span.start,
                end=span.end,
                overlap_len=span.overlap_len,
                offsets=tuple(inside_offsets),
                in_new_content=any(
                    offset + len(normalized) > span.overlap_len for offset in inside_offsets
                ),
            )
        )

    primary = next(
        (view for view in coverages if view.chunk_key == record.matched_chunk_key), None
    )
    before_context = inside_window = after_context = ""
    head_cut = tail_cut = False
    if primary is not None:
        before_context = chapter.text[
            max(0, primary.start - _NEIGHBOUR_CONTEXT) : primary.start
        ]
        after_context = chapter.text[primary.end : primary.end + _NEIGHBOUR_CONTEXT]
        anchor = primary.start + primary.offsets[0] if primary.offsets else primary.start
        window_start = max(primary.start, anchor - _INSIDE_WINDOW)
        window_end = min(primary.end, anchor + len(normalized) + _INSIDE_WINDOW)
        inside_window = chapter.text[window_start:window_end]
        head_cut = window_start > primary.start
        tail_cut = window_end < primary.end

    return ReviewRow(
        question_id=record.question_id,
        chapter_id=record.chapter_id,
        evidence=content,
        decision_tier=record.decision_tier,
        match_status=record.match_status,
        matched_chunk_key=record.matched_chunk_key,
        alternative_chunk_key=record.alternative_chunk_key,
        overlap_reason=record.overlap_reason,
        chapter_offsets=tuple(offsets),
        coverages=tuple(coverages),
        before_context=before_context,
        inside_window=inside_window,
        after_context=after_context,
        window_truncated_head=head_cut,
        window_truncated_tail=tail_cut,
    )


def _empty_row(record: MappingRecord, content: str) -> ReviewRow:
    return ReviewRow(
        question_id=record.question_id,
        chapter_id=record.chapter_id,
        evidence=content,
        decision_tier=record.decision_tier,
        match_status=record.match_status,
        matched_chunk_key=record.matched_chunk_key,
        alternative_chunk_key=record.alternative_chunk_key,
        overlap_reason=record.overlap_reason,
        chapter_offsets=(),
        coverages=(),
        before_context="",
        inside_window="",
        after_context="",
        window_truncated_head=False,
        window_truncated_tail=False,
    )


def write_review(review_dir: Path, rows: Sequence[ReviewRow], dataset_hash: str) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "review.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "question_id": row.question_id,
                    "chapter_id": row.chapter_id,
                    "evidence": row.evidence,
                    "decision_tier": row.decision_tier,
                    "match_status": row.match_status,
                    "matched_chunk_key": row.matched_chunk_key,
                    "alternative_chunk_key": row.alternative_chunk_key,
                    "overlap_reason": row.overlap_reason,
                    "chapter_offsets": list(row.chapter_offsets),
                    "coverages": [
                        {
                            "chunk_key": view.chunk_key,
                            "span": [view.start, view.end],
                            "overlap_len": view.overlap_len,
                            "evidence_offsets_in_chunk": list(view.offsets),
                            "in_new_content": view.in_new_content,
                        }
                        for view in row.coverages
                    ],
                },
                ensure_ascii=False,
            )
            for row in rows
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (review_dir / "review.md").write_text(
        _render(rows, dataset_hash), encoding="utf-8", newline="\n"
    )


def _render(rows: Sequence[ReviewRow], dataset_hash: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.decision_tier] = counts.get(row.decision_tier, 0) + 1
    attention = [row for row in rows if row.decision_tier != TIER_UNIQUE_COVER]

    lines = [
        "# evidence → chunk 映射 人工复核（冷启动 100%）",
        "",
        f"- dataset_hash：`{dataset_hash}`",
        f"- 复核对象：{len(rows)} 条 evidence",
        "",
        "## 先读这一节：怎么读下面的摘录",
        "",
        "映射用的是**章内区间包含**：evidence 是本项目语料里的原文片段，",
        "因此「哪个 chunk 包含它」由区间精确给出，不靠模型判断。",
        "你要确认的是**规则本身**，不是逐条重算。",
        "",
        "读摘录前必须知道的两件事：",
        "",
        "1. **overlap 在块首，不在块尾。** 每个 chunk 的开头会重复上一块的尾部",
        "   （最多 60 token，约 80–100 字）。所以「贴近块尾」恰恰说明它是**本块自己**的内容，",
        "   下一个块才会来重复它；反过来，「落在块首的重复段里」说明本块只是重述上一块。",
        "2. **块外文字不属于本块。** 下面凡标注 `⟨…不属于本块…⟩` 的片段都是邻块内容，",
        "   只是放在这里帮助判断 evidence 有没有跨过边界，**不要**把它当成主块正文。",
        "",
        "按复核成本分三档：",
        "",
    ]
    for tier, count in sorted(counts.items()):
        lines.append(f"- `{tier}`（{count} 条）：{_TIER_GUIDE.get(tier, '')}")

    lines.extend(
        [
            "",
            f"**需要逐条看的是 `{TIER_INTRODUCER}` 与 `{TIER_MAX_COVERAGE}`**，"
            f"共 {len(attention)} 条，已全部列在下面；",
            f"`{TIER_UNIQUE_COVER}` 的 {counts.get(TIER_UNIQUE_COVER, 0)} 条见 `review.jsonl`，",
            "抽看若干条能对上即可。",
            "",
            "## 需要逐条复核的条目",
            "",
        ]
    )

    if not attention:
        lines.append("（无）")
    for row in attention:
        lines.extend(_render_row(row))

    unmatched = [row for row in rows if row.match_status != MATCH_MATCHED]
    if unmatched:
        lines.extend(["## 未命中（必须处置，不得静默出分母）", ""])
        for row in unmatched:
            lines.append(f"- {row.question_id} ｜ {row.chapter_id}：{row.overlap_reason}")
        lines.append("")

    return "\n".join(lines)


def _render_row(row: ReviewRow) -> list[str]:
    lines = [
        f"### {row.question_id} ｜ {row.chapter_id} ｜ `{row.decision_tier}`",
        "",
        f"evidence（{len(row.evidence)} 字，章内出现 {len(row.chapter_offsets)} 次"
        + (f"：{list(row.chapter_offsets)}" if row.chapter_offsets else "")
        + "）",
        "",
        "```text",
        row.evidence,
        "```",
        "",
        "各覆盖块内的落点：",
        "",
    ]
    for view in row.coverages:
        role = "主块" if view.chunk_key == row.matched_chunk_key else "备选"
        offsets = "、".join(str(offset) for offset in view.offsets)
        if view.in_new_content:
            verdict = "✅ 落在本块**新增正文**内（本块是引入者）"
        else:
            verdict = "↩︎ 整段落在块首的重复段里（本块只是重述上一块）"
        lines.extend(
            [
                f"- **{role}** `{view.chunk_key}`：章内区间 [{view.start},{view.end})，"
                f"共 {view.end - view.start} 字，块首 {view.overlap_len} 字为重复上一块",
                f"  - evidence 在本块内的偏移：{offsets} → {verdict}",
            ]
        )
    lines.extend(["", f"- 判定：{row.overlap_reason}", ""])

    if row.inside_window:
        lines.extend(
            [
                "主块正文节选（`⟨…⟩` 内**不属于本块**，仅为判断边界之用）：",
                "",
                "```text",
            ]
        )
        if row.before_context:
            lines.append(f"⟨上一块尾部 {len(row.before_context)} 字⟩{row.before_context}")
        head = "…" if row.window_truncated_head else ""
        tail = "…" if row.window_truncated_tail else ""
        lines.append(f"⟨本块开始⟩{head}{row.inside_window}{tail}⟨本块结束⟩")
        if row.after_context:
            lines.append(f"⟨下一块开头 {len(row.after_context)} 字⟩{row.after_context}")
        lines.extend(["```", ""])

    return lines


_TIER_GUIDE = {
    TIER_UNIQUE_COVER: "章内只有一个 chunk 完整包含该证据——只需确认证据确实是原文片段",
    TIER_INTRODUCER: (
        "证据跨块边界，两块都完整包含。主块取**引入者**："
        "evidence 落在它新增正文里，另一个块只是把它放进了块首的重复段"
    ),
    TIER_MAX_COVERAGE: (
        "该证据在章内**出现多次且落在不同 chunk**，存在多个真实归属。"
        "主块取章内最早的块，其余记备选——**必须逐条看**"
    ),
}

"""按章分块（M0-01 §3.1）。

算法：

1. 先按段落换行、再按句子边界递归切分成「单元」，单元拼接回去等于原正文；
2. 句子是普通最小单位，单句超过 `max_chunk_tokens` 才按 token 硬切；
3. 每块以「上一块末尾的完整尾句」开头，最多 `overlap_tokens` 个 token；
   尾句本身超过 `overlap_tokens` 时取末尾 `overlap_tokens` 个 token 的窗口
   （「最多」优先于「完整尾句」）；
4. 每章独立成块：本函数只接收单章文本，`chunk_index` 章内从 0 起，prev/next 只在同章；
5. chunk 总长（含 overlap）不超过 `max_chunk_tokens`，故新增正文不超过
   `max_chunk_tokens - overlap_tokens`。

中文句子边界：句末标点为 `。！？!?…`，其后可紧跟收尾引号 / 括号（`」』）)】》〉”’"'`），
再接空白与换行；无标点的换行本身也作为段落边界。规则确定、可复现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from omniread.domain.text import chapter_content_hash
from omniread.infrastructure.tokenizer import TokenCounter, get_token_counter
from omniread.pipelines.chunking.profile import M0_PLACEHOLDER_V1, ChunkingProfile

# 句末标点。
_SENTENCE_TERMINATORS = "。！？!?…"
# 句末标点后可能紧跟的收尾引号 / 括号。
_SENTENCE_CLOSERS = "」』）)】》〉”’\"'"
# 一个单元 = 句末标点（含收尾引号/括号），其后**只有在真的跟着换行时**才吞掉行内空白与换行；
# 或纯换行（无标点的段落边界）。
#
# 「只有跟着换行才吞空白」是必需的：`chunk.content_hash` 按最小规范化后的正文算，
# 而最小规范化会去掉行尾空白。若单元在**没有换行**的情况下也吞掉尾随空格，
# 该空格就会落在 chunk 末尾、留在存储字节里，于是 `sha256(content)` 与 `content_hash` 对不上
# （全库曾出现 1/1807 行），任何按字节校验完整性的检查都会误报。
_SENTENCE_BOUNDARY = re.compile(
    rf"[{_SENTENCE_TERMINATORS}]+[{_SENTENCE_CLOSERS}]*(?:[ \t]*\n+)?|\n+"
)


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """一章里的一个 chunk；`chunk_index` 章内从 0 起。"""

    chunk_key: str
    chapter_id: str
    chunk_index: int
    content: str
    token_count: int
    content_hash: str
    prev_chunk_key: str | None
    next_chunk_key: str | None


def split_sentences(text: str) -> list[str]:
    """切成句子单元；`"".join(result) == text`，不丢任何字符。"""
    units: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        end = match.end()
        units.append(text[start:end])
        start = end
    if start < len(text):
        units.append(text[start:])
    return units


def chunk_chapter(
    chapter_id: str,
    text: str,
    profile: ChunkingProfile = M0_PLACEHOLDER_V1,
    counter: TokenCounter | None = None,
) -> list[ChunkDraft]:
    """把一章的规范化正文切成 chunk 列表。

    `text` 是单章正文，因此结果天然不跨章；`chunk_key` 由 `chapter_id` 派生。
    """
    if profile.cross_chapter:
        raise ValueError("分块只接收单章正文，profile 不允许 cross_chapter=True")
    used_counter = counter if counter is not None else get_token_counter()
    contents = _assemble_contents(text, profile, used_counter)
    drafts: list[ChunkDraft] = []
    for index, content in enumerate(contents):
        drafts.append(
            ChunkDraft(
                chunk_key=_chunk_key(chapter_id, index),
                chapter_id=chapter_id,
                chunk_index=index,
                content=content,
                token_count=used_counter.count(content),
                content_hash=chapter_content_hash(content),
                prev_chunk_key=_chunk_key(chapter_id, index - 1) if index > 0 else None,
                next_chunk_key=(
                    _chunk_key(chapter_id, index + 1) if index + 1 < len(contents) else None
                ),
            )
        )
    return drafts


def _chunk_key(chapter_id: str, chunk_index: int) -> str:
    return f"{chapter_id}#c{chunk_index}"


def _assemble_contents(
    text: str, profile: ChunkingProfile, counter: TokenCounter
) -> list[str]:
    """贪心装配：每块 = 上一块尾部 overlap（≤60 token）+ 新增正文，总长 ≤600。"""
    hard_limit = max(1, profile.max_chunk_tokens - profile.overlap_tokens)
    chunks: list[str] = []
    parts: list[str] = []
    new_tokens = 0
    budget = profile.max_chunk_tokens

    def flush() -> None:
        nonlocal new_tokens, budget
        if parts:
            chunks.append("".join(parts))
            parts.clear()
        new_tokens = 0
        budget = profile.max_chunk_tokens

    for unit in split_sentences(text):
        unit_tokens = counter.count(unit)
        if unit_tokens > profile.max_chunk_tokens:
            # 超长句：先冲掉手头的块，再按 token 硬切，片间沿用尾 overlap。
            flush()
            for piece in counter.split_to_limit(unit, hard_limit):
                overlap = (
                    _tail_overlap(chunks[-1], profile, counter) if chunks else ""
                )
                chunks.append(overlap + piece)
            continue
        if parts and new_tokens + unit_tokens <= budget:
            parts.append(unit)
            new_tokens += unit_tokens
            continue
        if parts:
            flush()
        overlap = _tail_overlap(chunks[-1], profile, counter) if chunks else ""
        overlap_tokens = counter.count(overlap)
        if unit_tokens <= profile.max_chunk_tokens - overlap_tokens:
            if overlap:
                parts.append(overlap)
            budget = profile.max_chunk_tokens - overlap_tokens
        else:
            # 单句本身接近上限，再加 overlap 就超限：本块不带头 overlap。
            budget = profile.max_chunk_tokens
        parts.append(unit)
        new_tokens = unit_tokens
    flush()
    return chunks


def _tail_overlap(content: str, profile: ChunkingProfile, counter: TokenCounter) -> str:
    """取一块末尾的 overlap：优先完整尾句，尾句超长时取末尾 token 窗。"""
    if not content:
        return ""
    if counter.count(content) <= profile.overlap_tokens:
        return content
    collected: list[str] = []
    total = 0
    for unit in reversed(split_sentences(content)):
        unit_tokens = counter.count(unit)
        if total + unit_tokens > profile.overlap_tokens:
            break
        collected.append(unit)
        total += unit_tokens
    if collected:
        return "".join(reversed(collected))
    return counter.tail(content, profile.overlap_tokens)

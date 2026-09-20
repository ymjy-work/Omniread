"""把一章的 chunk 正文还原成章内字符区间。

区间包含是确定性映射的全部依据，所以这里对不变量**显式断言、失败即报错**：
若某个 chunk 的正文不是本章正文的连续切片，区间无从谈起，任何「尽力而为」的兜底
都会产出看似合理的错误映射——那比直接失败危险得多。

起点不用 `text.find` 推：正文里存在重复段落时，`find` 会落到更早的同文位置，
区间随之错位（同一句话反复出现的章节就会踩到）。改为按 chunker 的构造方式反推——
chunk i 以 chunk i-1 的尾 overlap 开头，故第一步取「既是 chunk i-1 后缀、又是 chunk i
前缀」的最长串，起点即 `上一块终点 − 该长度`；首块起点为 0。
推出来之后再拿原文校验一次，确保推的不是自洽的空想。
"""

from __future__ import annotations

from collections.abc import Sequence

from omniread.pipelines.mapping.types import ChunkSpan


class ChunkSpanError(ValueError):
    """chunk 正文与章节正文对不上：区间不可用，映射必须整体失败而非降级。"""


def spans_from_contents(
    chapter_id: str,
    text: str,
    contents: Sequence[str],
) -> list[ChunkSpan]:
    """把按 `chunk_index` 升序的 chunk 正文还原为区间列表。

    任一区间与原文对不上即抛 `ChunkSpanError`——包括中间某块对不上、后继块连锁错位的情形。
    """
    spans: list[ChunkSpan] = []
    prev_content = ""
    prev_end = 0

    for index, content in enumerate(contents):
        if index == 0:
            start = 0
            overlap_len = 0
        else:
            overlap_len = _overlap_len(prev_content, content)
            start = prev_end - overlap_len
        end = start + len(content)

        if start < 0 or end > len(text) or text[start:end] != content:
            raise ChunkSpanError(
                f"{chapter_id}#c{index}: 正文不是本章正文的连续切片"
                f"（推算区间 [{start},{end})，章长 {len(text)}，块长 {len(content)}）"
            )

        spans.append(
            ChunkSpan(
                chunk_key=f"{chapter_id}#c{index}",
                chapter_id=chapter_id,
                chunk_index=index,
                start=start,
                end=end,
                overlap_len=overlap_len,
            )
        )
        prev_content = content
        prev_end = end

    return spans


def _overlap_len(previous: str, content: str) -> int:
    """「既是上一块后缀、又是本块前缀」的最长串长度；本块不带头部 overlap 时为 0。

    不封顶到 `overlap_tokens` 的换算值：token 与字符的换算随文本构成浮动，
    封顶一旦偏小会让真重叠被截短、区间整体前移。降序试探配 `startswith` 的短路，
    实际代价是「每块若干次首字符即失败的比较」。
    """
    limit = min(len(previous), len(content))
    for length in range(limit, 0, -1):
        if content.startswith(previous[-length:]):
            return length
    return 0

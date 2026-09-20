"""上下文装配（M0-4）：先限章（≤8）→ 每章 ≤2 段（hit 优先、邻居补位）→ 截断 ≤8 段
→ realm re-check → token budget。

顺序不可调换，参数关系见 M0-00 §5；补位固定一跳、同章、prev 优先，见 M0-01 §4.3。
"""

from __future__ import annotations

from omniread.pipelines.assembly.assembler import (
    REASON_CHAPTER_CAP,
    REASON_CHAPTER_CHUNK_CAP,
    REASON_MISSING_CHUNK,
    REASON_REALM,
    REASON_TOKEN_BUDGET,
    REASON_TOP_K_CAP,
    AssembledChunk,
    AssemblyResult,
    ChunkCandidate,
    DroppedChunk,
    Neighborhood,
    Source,
    assemble,
)

__all__ = [
    "REASON_CHAPTER_CAP",
    "REASON_CHAPTER_CHUNK_CAP",
    "REASON_MISSING_CHUNK",
    "REASON_REALM",
    "REASON_TOKEN_BUDGET",
    "REASON_TOP_K_CAP",
    "AssembledChunk",
    "AssemblyResult",
    "ChunkCandidate",
    "DroppedChunk",
    "Neighborhood",
    "Source",
    "assemble",
]

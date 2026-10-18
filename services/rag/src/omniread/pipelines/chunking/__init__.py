"""分块：按章切分、不跨章，token 口径 600 / 60 重叠，profile `m0-placeholder-v1`。

规则与 `chunk_key` 口径见 `chunker.py`。
"""

from __future__ import annotations

from omniread.pipelines.chunking.chunker import (
    ChunkDraft,
    chunk_chapter,
    split_sentences,
)
from omniread.pipelines.chunking.profile import M0_PLACEHOLDER_V1, ChunkingProfile

__all__ = [
    "M0_PLACEHOLDER_V1",
    "ChunkDraft",
    "ChunkingProfile",
    "chunk_chapter",
    "split_sentences",
]

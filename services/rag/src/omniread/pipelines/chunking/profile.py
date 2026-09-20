"""分块 profile：冻结的 `m0-placeholder-v1` 参数（M0-01 §3.1）。

参数值一次定死；改这些值等于换 chunk profile，chunk_key 与 chunk_mappings 全部失效。
运行参数不要散落成魔法数，统一从这里取。
"""

from __future__ import annotations

from dataclasses import dataclass

from omniread.infrastructure.tokenizer import TOKENIZER_ID


@dataclass(frozen=True, slots=True)
class ChunkingProfile:
    """一次分块的全部口径；`profile_id` 即写入 chunks 的 `chunking_version`。"""

    profile_id: str
    # 计量单位：token（与 max_chunk_tokens / overlap_tokens 同口径）。
    unit: str
    # chunk 总长（含 overlap）上限。
    max_chunk_tokens: int
    overlap_tokens: int
    cross_chapter: bool
    tokenizer_id: str
    sentence_boundary: str
    hanzi_per_600_tokens: float
    tokenizer_error_median: float
    tokenizer_error_max: float


M0_PLACEHOLDER_V1 = ChunkingProfile(
    profile_id="m0-placeholder-v1",
    unit="token",
    max_chunk_tokens=600,
    overlap_tokens=60,
    cross_chapter=False,
    tokenizer_id=TOKENIZER_ID,
    sentence_boundary="preferred",
    # 本语料实测的汉字口径换算（排除标点 / 拉丁 / 换行），误差相对线上 embedding 分词器。
    hanzi_per_600_tokens=738.7,
    tokenizer_error_median=0.0,
    tokenizer_error_max=0.0,
)

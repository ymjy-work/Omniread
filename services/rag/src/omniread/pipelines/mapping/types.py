"""映射模块的数据形状（M0-02 §6）。

`chunk_mappings` 的列与这里的字段一一对应；`MappingOutcome` 同时是落库行与 run 产物行，
两者共用一份结构，避免「库里一套、产物里一套」对不上。
"""

from __future__ import annotations

from dataclasses import dataclass

# 投影模型契约住在 infrastructure/providers/base.py（与 ChatModel / EmbeddingModel 同级）。
# 这里只做转出，方便调用方从 mapping 包一处取齐所需的类型。
from omniread.infrastructure.providers.base import MapperCandidate, MapperResult

__all__ = [
    "DETERMINISTIC_MAPPER_MODEL",
    "MATCH_LOW_CONF",
    "MATCH_MATCHED",
    "MATCH_UNMATCHED",
    "NO_PROMPT_VERSION",
    "ChunkSpan",
    "MapperCandidate",
    "MapperResult",
    "MappingOutcome",
]

MATCH_MATCHED = "matched"
MATCH_LOW_CONF = "low_conf"
MATCH_UNMATCHED = "unmatched"

# 确定性映射的 mapper_model 取值。它是 `chunk_mappings` 五元组主键的分量，
# 改动即所有确定性映射失效，因此带版本后缀、且算法变更时必须同时改这里。
DETERMINISTIC_MAPPER_MODEL = "deterministic:substring-interval-v1"

# 确定性路径没有 prompt，但 `mapper_prompt_version` 是非空主键分量，必须给一个取值。
# 用显式的占位串而不是空串：空串在库里看起来像「漏填」，而它其实是一个确定的结论——
# 这条映射不是由 prompt 产生的，因此不随任何 prompt 变更而失效。
NO_PROMPT_VERSION = "no-prompt"


@dataclass(frozen=True, slots=True)
class ChunkSpan:
    """一个 chunk 在**本章规范化正文**中的连续区间。

    `split_sentences` 保证单元拼接等于原文，chunk 是单元序列（可能带上一块的尾 overlap），
    因此每个 chunk 的正文必然等于 `text[start:end]`——区间是 chunk 身份的等价描述。
    """

    chunk_key: str
    chapter_id: str
    chunk_index: int
    start: int
    end: int
    # 本块开头有多少字符属于**上一块**的尾部（overlap）；首块为 0。
    overlap_len: int


@dataclass(frozen=True, slots=True)
class MappingOutcome:
    """一条 evidence 的映射结果；字段集 = `chunk_mappings` 的全部业务列。"""

    evidence_hash: str
    chapter_id: str
    match_status: str
    matched_chunk_key: str | None
    confidence: float
    overlap_reason: str
    alternative_chunk_key: str | None
    mapper_model: str
    mapper_prompt_version: str
    # 命中判据的档位，仅用于诊断与抽样复核：「unique_cover」= 恰好一个 chunk 覆盖；
    # 「introducer」= 多块覆盖但只有一个引入者；「fallback_*」= 退到兜底规则。
    decision_tier: str = ""

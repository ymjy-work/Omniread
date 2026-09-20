"""检索链的进程内数据类型。

`ChunkRecord` 是检索侧对一行 chunk 的视图，只带链路上用得到的列（正文、token 数、
同章邻居键）；`StageHit` 是逐阶段列表的元素；`RetrievalOutcome` 是一次检索的全部产物，
`retrieval-only` 端点按它直接映射契约载荷。

不在这里放「截断过的 top 列表」——`retrieval-only` 要求逐阶段完整、不截断，
截断只发生在装配的最后一步。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from omniread.pipelines.assembly import AssembledChunk, DroppedChunk
from omniread.pipelines.params import M0_PARAMS, RetrievalParams
from omniread.pipelines.retrieval.query import RealmBounds

# 逐阶段列表的元素：`rank` 从 1 起，`score` 是该阶段自己的量纲（余弦相似度 / BM25 分 /
# RRF 分 / rerank 分），跨阶段不可比。
ScoredStage = Literal["dense", "kw", "fused", "rerank"]


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    """一个 chunk 的检索视图；`prev_chunk_key` / `next_chunk_key` 只指向同章邻居。"""

    chunk_key: str
    chapter_index: int
    chunk_index: int
    content: str
    token_count: int
    prev_chunk_key: str | None
    next_chunk_key: str | None


@dataclass(frozen=True, slots=True)
class StageHit:
    """某一路检索的一条命中。`chapter_index` 冗余携带，省掉逐阶段再查一次 chunk。"""

    chunk_key: str
    chapter_index: int
    score: float
    rank: int


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """一次检索链的完整结果，逐阶段不截断。

    `assembled` 是最终进入 prompt 的集合（realm re-check 与 token budget 均已结算），
    按 `chunk_index` 升序呈现；被裁项在 `dropped`。逐阶段列表是诊断用，指标命中判定
    以 `assembled` 为准（M0-02 §8.7）。
    """

    query: str
    realm: RealmBounds
    dense: tuple[StageHit, ...]
    kw: tuple[StageHit, ...]
    fused: tuple[StageHit, ...]
    reranked: tuple[StageHit, ...]
    assembled: tuple[AssembledChunk, ...]
    dropped: tuple[DroppedChunk, ...]
    token_estimate: int
    params: RetrievalParams = M0_PARAMS


__all__ = ["ChunkRecord", "RetrievalOutcome", "ScoredStage", "StageHit"]

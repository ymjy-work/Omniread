"""检索（M0-4）：normalize → realm → dense(top60) → BM25(top60) → RRF(k=60) → rerank。

链路口径见 M0-01 §4；realm 过滤与迭代索引扫描的约束同见该节。装配在
`omniread.pipelines.assembly`，本包只负责把候选池交出去。
"""

from __future__ import annotations

from omniread.pipelines.retrieval.bm25 import DEFAULT_KW_K, Bm25Index, KeywordHit, tokenize
from omniread.pipelines.retrieval.dense import DenseHit, DenseIndex, PgVectorDenseIndex
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline
from omniread.pipelines.retrieval.query import RealmBounds, normalize_query, resolve_realm
from omniread.pipelines.retrieval.rerank import RerankHit, rerank_candidates
from omniread.pipelines.retrieval.rrf import RRF_K, FusedHit, reciprocal_rank_fusion
from omniread.pipelines.retrieval.store import ChunkStore, PgChunkStore
from omniread.pipelines.retrieval.types import ChunkRecord, RetrievalOutcome, StageHit

__all__ = [
    "DEFAULT_KW_K",
    "RRF_K",
    "Bm25Index",
    "ChunkRecord",
    "ChunkStore",
    "DenseHit",
    "DenseIndex",
    "FusedHit",
    "KeywordHit",
    "PgChunkStore",
    "PgVectorDenseIndex",
    "RealmBounds",
    "RerankHit",
    "RetrievalOutcome",
    "RetrievalPipeline",
    "StageHit",
    "normalize_query",
    "reciprocal_rank_fusion",
    "rerank_candidates",
    "resolve_realm",
    "tokenize",
]

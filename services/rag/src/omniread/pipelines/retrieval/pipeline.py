"""查询链编排（M0-01 §4.1）。

```text
normalize（NFC → trim → 空白折叠）
→ （不 rewrite）
→ realm bounds
→ dense top60
→ BM25 top60
→ RRF(k=60)
→ rerank 入 24 / 出 24
→ 装配（章 ≤8、每章 ≤2 段）
```

几条口径在代码里的落点：

- **realm**：dense 交给 SQL `WHERE`，BM25 用 `allowed_keys` 在打分前收窄候选；两条路都
  只把 realm 当过滤器，BM25 的统计量仍取自全书。
- **可检索行**：dense 只认 `embedding IS NOT NULL`（见 `dense.py`）；未嵌入时 dense 一路
  召回 0 条，链路照常由 BM25 走通——这是预期行为，不是故障。
- **装配顺序**：先限章 → 再限每章段数 → 最后按 rerank 序截断，见 `assembly`。

DB 访问是同步 SQLAlchemy，统一走 `asyncio.to_thread`：provider 调用是异步的（httpx），
同步查询直接放在协程里会占住事件循环。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from omniread.domain.errors import RagInvalidRealm
from omniread.domain.models import QueryRequest
from omniread.infrastructure.db.models import EMBEDDING_DIM
from omniread.infrastructure.providers.base import EmbeddingModel, RerankModel
from omniread.infrastructure.providers.errors import ProviderResponseError
from omniread.pipelines.assembly import ChunkCandidate, assemble
from omniread.pipelines.params import M0_PARAMS, RetrievalParams
from omniread.pipelines.retrieval.bm25 import Bm25Index
from omniread.pipelines.retrieval.dense import DenseIndex
from omniread.pipelines.retrieval.query import normalize_query, resolve_realm
from omniread.pipelines.retrieval.rerank import rerank_candidates
from omniread.pipelines.retrieval.rrf import reciprocal_rank_fusion
from omniread.pipelines.retrieval.store import ChunkStore
from omniread.pipelines.retrieval.types import ChunkRecord, RetrievalOutcome, StageHit

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """一次检索的编排者：持有 store / dense / provider，进程内复用。"""

    def __init__(
        self,
        *,
        store: ChunkStore,
        dense: DenseIndex,
        embedder: EmbeddingModel,
        reranker: RerankModel,
        params: RetrievalParams = M0_PARAMS,
    ) -> None:
        if embedder.dim != EMBEDDING_DIM:
            raise ValueError(
                f"embedding 维度必须是 {EMBEDDING_DIM}，实际 {embedder.dim}："
                "与 chunks.embedding 列维度绑定，不一致时检索结果不可用"
            )
        self._store = store
        self._dense = dense
        self._embedder = embedder
        self._reranker = reranker
        self._params = params
        # BM25 索引常驻：构建要分词全书，逐请求重建不可接受。按 book 缓存并用
        # chunk_key 集合的 sha256 做指纹，导入换了语料即失效。
        self._bm25_cache: dict[int, tuple[str, Bm25Index]] = {}

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome:
        """跑完整条查询链，返回逐阶段结果与最终装配集。"""
        params = self._params
        query = normalize_query(request.question)
        if not query:
            raise RagInvalidRealm("查询为空")

        records = await asyncio.to_thread(self._store.load_chunks, request.book_id)
        if not records:
            raise RagInvalidRealm("本书没有可检索的 chunk")
        chapter_range = await asyncio.to_thread(
            self._store.book_chapter_range, request.book_id
        )
        if chapter_range is None:
            raise RagInvalidRealm("本书没有章节")
        realm = resolve_realm(
            request.level,
            request.progress,
            chapter_min=chapter_range[0],
            chapter_max=chapter_range[1],
        )

        by_key = {record.chunk_key: record for record in records}
        realm_keys = {
            record.chunk_key for record in records if realm.contains(record.chapter_index)
        }

        # BM25：统计量全局，realm 只收窄候选（M0-01 §4.2）。
        index = await asyncio.to_thread(self._bm25_index, request.book_id, records)
        kw_ranked = _stage_hits(
            user=index.search(query, k=params.kw_k, allowed_keys=realm_keys),
            by_key=by_key,
            key_of=lambda hit: hit.chunk_key,
            score_of=lambda hit: hit.score,
        )

        # dense：realm 与 embedding IS NOT NULL 都在 SQL WHERE 里。
        vector = await self._embedder.embed_query(query)
        if len(vector) != EMBEDDING_DIM:
            raise ProviderResponseError(
                f"查询向量维度不是 {EMBEDDING_DIM}", provider=self._embedder.model
            )
        dense_hits = await asyncio.to_thread(
            partial(
                self._dense.search,
                vector,
                book_id=request.book_id,
                lo=realm.lo,
                hi=realm.hi,
                k=params.dense_k,
            )
        )
        dense_ranked = _stage_hits(
            user=dense_hits,
            by_key=by_key,
            key_of=lambda hit: hit.chunk_key,
            score_of=lambda hit: hit.score,
        )

        # RRF：只吃排名，避开两路分数量纲不可比的问题。
        fused_hits = reciprocal_rank_fusion(
            {
                "dense": [hit.chunk_key for hit in dense_ranked],
                "kw": [hit.chunk_key for hit in kw_ranked],
            },
            k=params.rrf_k,
        )
        fused_ranked = tuple(
            StageHit(
                chunk_key=hit.chunk_key,
                chapter_index=by_key[hit.chunk_key].chapter_index,
                score=hit.score,
                rank=hit.rank,
            )
            for hit in fused_hits
        )

        # rerank：入 24 出 24，再进装配。
        pool = fused_ranked[: params.rerank_k]
        reranked = await self._rerank(query, pool, by_key)

        assembly = assemble(
            [
                ChunkCandidate(chunk_key=hit.chunk_key, score=hit.score, rank=hit.rank)
                for hit in reranked
            ],
            chunks=by_key,
            realm=realm,
            params=params,
            expand_neighbors=request.neighbor_expand,
        )

        logger.info(
            "检索完成 book=%s realm=[%s,%s] dense=%d kw=%d fused=%d rerank=%d assembled=%d",
            request.book_id,
            realm.lo,
            realm.hi,
            len(dense_ranked),
            len(kw_ranked),
            len(fused_ranked),
            len(reranked),
            len(assembly.chunks),
        )
        return RetrievalOutcome(
            query=query,
            realm=realm,
            dense=dense_ranked,
            kw=kw_ranked,
            fused=fused_ranked,
            reranked=reranked,
            assembled=assembly.chunks,
            dropped=assembly.dropped,
            token_estimate=assembly.token_estimate,
            params=params,
        )

    async def _rerank(
        self, query: str, pool: Sequence[StageHit], by_key: dict[str, ChunkRecord]
    ) -> tuple[StageHit, ...]:
        hits = await rerank_candidates(
            self._reranker,
            query,
            [(hit.chunk_key, by_key[hit.chunk_key].content) for hit in pool],
            top_n=self._params.rerank_output,
        )
        return tuple(
            StageHit(
                chunk_key=hit.chunk_key,
                chapter_index=by_key[hit.chunk_key].chapter_index,
                score=hit.score,
                rank=rank,
            )
            for rank, hit in enumerate(hits, start=1)
        )

    def _bm25_index(self, book_id: int, records: Sequence[ChunkRecord]) -> Bm25Index:
        """按书缓存 BM25 索引；chunk_key 集合变化即重建。"""
        fingerprint = hashlib.sha256(
            "\n".join(record.chunk_key for record in records).encode("utf-8")
        ).hexdigest()
        cached = self._bm25_cache.get(book_id)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        index = Bm25Index(
            [record.chunk_key for record in records],
            [record.content for record in records],
        )
        self._bm25_cache[book_id] = (fingerprint, index)
        return index


def _stage_hits(
    *,
    user: Sequence[Any],
    by_key: dict[str, ChunkRecord],
    key_of: Callable[[Any], str],
    score_of: Callable[[Any], float],
) -> tuple[StageHit, ...]:
    """把某一路的命中映射成 `StageHit`，名次就是返回顺序（下标 + 1）。

    命中不在本次加载的 chunk 视图里时跳过：视图与另一路查询之间若发生导入，
    缺正文的候选进不了 rerank，硬取会在这里抛 KeyError 而不是给出可定位的错。
    """
    hits: list[StageHit] = []
    for position, item in enumerate(user, start=1):
        chunk_key = key_of(item)
        record = by_key.get(chunk_key)
        if record is None:
            continue
        hits.append(
            StageHit(
                chunk_key=chunk_key,
                chapter_index=record.chapter_index,
                score=score_of(item),
                rank=position,
            )
        )
    return tuple(hits)


__all__ = ["RetrievalPipeline"]

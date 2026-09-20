"""向量召回：pgvector 余弦距离 + HNSW 索引（M0-01 §4.2，M0-02 §3.8）。

查询形状：

```sql
SELECT chunk_key, embedding <=> :q AS distance
FROM chunks
WHERE book_id = :book_id
  AND embedding IS NOT NULL
  AND chapter_index BETWEEN :lo AND :hi
ORDER BY distance
LIMIT :k
```

三条都是硬要求：

- **realm 在 SQL `WHERE` 里过滤**（`chapter_index`），不是取回候选再在应用层筛。
- **`embedding IS NOT NULL`**：未嵌入的行在余弦距离下会得到 NULL，参与排序时既不报错
  也不入选，等于静默漏召回。显式排除才能让「还没嵌入」变成一个可见事实。
- **向量维度 1024**：与 `chunks.embedding` 列维度绑定，执行前校验；维度不符直接报错，
  让 pgvector 的距离运算抛错会把问题藏进 SQL 层。

`ORDER BY embedding <=> :q LIMIT k` 是 HNSW 索引的可用形状；realm 过滤条件无法下推进
索引内部，所以会话必须开 `hnsw.iterative_scan` 与足够的 `ef_search`
（`infrastructure/db/session.py` 在连接建立时下发），否则窄域过滤会召回不齐。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from omniread.infrastructure.db.models import EMBEDDING_DIM, Chunk


@dataclass(frozen=True, slots=True)
class DenseHit:
    """一条向量命中。`score` 是余弦相似度（`1 - 余弦距离`），越大越相近。"""

    chunk_key: str
    score: float


class DenseIndex(Protocol):
    """向量召回接口；测试用内存实现替换。"""

    def search(
        self, query_vector: Sequence[float], *, book_id: int, lo: int, hi: int, k: int
    ) -> Sequence[DenseHit]:
        """取 book 内 `chapter_index` 落在 `[lo, hi]` 且已嵌入的前 k 条。"""
        ...


class PgVectorDenseIndex:
    """pgvector 实现。`session_factory` 由调用方给，每次查询开一个会话。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def search(
        self, query_vector: Sequence[float], *, book_id: int, lo: int, hi: int, k: int
    ) -> Sequence[DenseHit]:
        if k <= 0:
            raise ValueError("k 必须为正整数")
        if len(query_vector) != EMBEDDING_DIM:
            raise ValueError(
                f"查询向量维度必须是 {EMBEDDING_DIM}，实际 {len(query_vector)}："
                "与 chunks.embedding 列维度绑定，不一致时距离比较不可信"
            )
        distance = Chunk.embedding.cosine_distance(list(query_vector)).label("distance")
        statement = (
            select(Chunk.chunk_key, distance)
            .where(
                Chunk.book_id == book_id,
                Chunk.embedding.is_not(None),
                Chunk.chapter_index >= lo,
                Chunk.chapter_index <= hi,
            )
            .order_by(distance)
            .limit(k)
        )
        with self._session_factory() as session:
            rows = session.execute(statement).all()
        return [DenseHit(chunk_key=row.chunk_key, score=1.0 - float(row.distance)) for row in rows]


__all__ = ["DenseHit", "DenseIndex", "PgVectorDenseIndex"]

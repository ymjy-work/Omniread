"""chunk 读取：全书视图与章节范围。

一次查询把 book 的全部 chunk 读进内存：BM25 索引需要全书正文、统计量必须全局
（M0-01 §4.2），邻块补位又只查同章邻居——两者都从这份视图里取，装配不再回库。
M0 的规模是单本 1807 个 chunk，这个量级下内存与一次全表读都可接受；
换到多书 / 大语料时再改成按书缓存与增量索引。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from omniread.infrastructure.db.models import Chapter, Chunk
from omniread.pipelines.retrieval.types import ChunkRecord


class ChunkStore(Protocol):
    """检索侧读 chunk 的唯一入口；测试用内存实现替换。"""

    def book_chapter_range(self, book_id: int) -> tuple[int, int] | None:
        """本书的最小 / 最大 `chapter_index`；书不存在或没有章节时返回 None。"""
        ...

    def load_chunks(self, book_id: int) -> Sequence[ChunkRecord]:
        """全书 chunk，按 `(chapter_index, chunk_index)` 升序。"""
        ...


class PgChunkStore:
    """PostgreSQL 实现。`session_factory` 由调用方给，便于在检索链里按调用开闭会话。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def book_chapter_range(self, book_id: int) -> tuple[int, int] | None:
        # 章节范围取自 chapters 表：realm 的边界是章节语义，不是「有 chunk 的章节」。
        with self._session_factory() as session:
            row = session.execute(
                select(func.min(Chapter.chapter_index), func.max(Chapter.chapter_index)).where(
                    Chapter.book_id == book_id
                )
            ).one()
        low, high = row
        if low is None or high is None:
            return None
        return int(low), int(high)

    def load_chunks(self, book_id: int) -> Sequence[ChunkRecord]:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    Chunk.chunk_key,
                    Chunk.chapter_index,
                    Chunk.chunk_index,
                    Chunk.content,
                    Chunk.token_count,
                    Chunk.prev_chunk_key,
                    Chunk.next_chunk_key,
                )
                .where(Chunk.book_id == book_id)
                .order_by(Chunk.chapter_index, Chunk.chunk_index)
            ).all()
        return [
            ChunkRecord(
                chunk_key=row.chunk_key,
                chapter_index=row.chapter_index,
                chunk_index=row.chunk_index,
                content=row.content,
                token_count=row.token_count,
                prev_chunk_key=row.prev_chunk_key,
                next_chunk_key=row.next_chunk_key,
            )
            for row in rows
        ]


__all__ = ["ChunkStore", "PgChunkStore"]

"""装配集正文读取：chunk 内容 + 所属章标题。

检索链只用 chunk 做召回复算，正文用完即弃；组装回答 prompt 需要正文，`context_chapters`
又需要章标题，因此这里用一次 JOIN 把两者取回。只读，不做过滤与截断——裁剪已在装配阶段
完成，`chunk_keys` 就是最终进入 prompt 的集合。
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from omniread.domain.models import ContextChunk
from omniread.infrastructure.db.models import Chapter, Chunk


class PgContextSource:
    """`ContextSource` 的 PostgreSQL 实现。`session_factory` 由调用方给，便于按调用开闭会话。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
        keys = list(chunk_keys)
        if not keys:
            # 空装配集（拒答路径）不必查库，IN () 也不是合法 SQL。
            return []
        with self._session_factory() as session:
            rows = session.execute(
                select(Chunk.chunk_key, Chunk.chapter_index, Chapter.title, Chunk.content)
                .join(Chapter, Chunk.chapter_id == Chapter.chapter_id)
                .where(Chunk.book_id == book_id, Chunk.chunk_key.in_(keys))
            ).all()
        return [
            ContextChunk(
                chunk_key=row.chunk_key,
                chapter_index=row.chapter_index,
                chapter_title=row.title,
                text=row.content,
            )
            for row in rows
        ]


__all__ = ["PgContextSource"]

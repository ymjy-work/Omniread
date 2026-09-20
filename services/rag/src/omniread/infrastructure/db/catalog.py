"""CatalogRepository 的 PostgreSQL 实现与空实现。

catalog 端点读的是导入落库的 `books` / `volumes` / `chapters`；空实现用于
「库未接线」或测试注入，返回真实空结构而不是假数据——空结构能被前端与网关正常解析，
也不会被误当成真实结果。

章节详情的 `images` 由 `chapters.image_paths` 现场重建：marker 取文件主干、url 拼成
外部的网关插图端点，前端拿到即可直接喂给 `<img src>`。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from omniread.domain.models import BookSummary, ChapterDetail, ChapterSummary, ImageRef
from omniread.infrastructure.db.models import Book, Chapter, Volume
from omniread.infrastructure.objectstore.paths import strip_corpus_images_prefix

# 对外插图端点的前缀；url 是外部契约形状，前端经 Java 网关取字节。
_PUBLIC_IMAGES_PATH = "/api/v1/books"


def build_image_refs(book_id: int, image_paths: Sequence[str]) -> tuple[ImageRef, ...]:
    """语料相对路径 → `{marker, url}`。

    - marker 取文件主干：`images/01_第1卷/007.jpg` → `"007"`，与正文里 `[插图007]` 的编号对齐；
    - url 去掉语料自带的 `images/` 前缀，拼成 `/api/v1/books/{book_id}/images/{相对路径}`，
      即 M0-02 §8.8 的契约形状（前端直接用作 `<img src>`）。
    """
    return tuple(
        # 语料路径一律 POSIX 风格，用 PurePosixPath 取主干，不受宿主平台影响。
        ImageRef(marker=PurePosixPath(path).stem, url=_illustration_url(book_id, path))
        for path in image_paths
    )


def _illustration_url(book_id: int, corpus_relative: str) -> str:
    relative = strip_corpus_images_prefix(corpus_relative)
    return f"{_PUBLIC_IMAGES_PATH}/{book_id}/images/{relative}"


class PgCatalogRepository:
    """读库实现。查询同步，路由是同步处理器，由 FastAPI 放进线程池执行。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_books(self) -> Sequence[BookSummary]:
        chapter_count = (
            select(func.count())
            .select_from(Chapter)
            .where(Chapter.book_id == Book.id)
            .scalar_subquery()
        )
        volume_count = (
            select(func.count())
            .select_from(Volume)
            .where(Volume.book_id == Book.id)
            .scalar_subquery()
        )
        with self._session_factory() as session:
            rows = session.execute(
                select(Book, chapter_count, volume_count).order_by(Book.id)
            ).all()
        return [
            BookSummary(
                book_id=book.id,
                title=book.title,
                author=book.author,
                chapter_count=chapters,
                volume_count=volumes,
            )
            for book, chapters, volumes in rows
        ]

    def list_chapters(self, book_id: int) -> Sequence[ChapterSummary]:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    Chapter.chapter_index,
                    Chapter.title,
                    Volume.volume_index,
                    Volume.title,
                )
                .join(Volume, Chapter.volume_id == Volume.id)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.chapter_index)
            ).all()
        return [
            ChapterSummary(
                chapter_index=chapter_index,
                chapter_title=chapter_title,
                volume_index=volume_index,
                volume_title=volume_title,
            )
            for chapter_index, chapter_title, volume_index, volume_title in rows
        ]

    def get_chapter(self, book_id: int, chapter_index: int) -> ChapterDetail | None:
        with self._session_factory() as session:
            row = session.execute(
                select(Chapter, Volume.volume_index, Volume.title)
                .join(Volume, Chapter.volume_id == Volume.id)
                .where(Chapter.book_id == book_id, Chapter.chapter_index == chapter_index)
            ).first()
            if row is None:
                return None
            chapter, volume_index, volume_title = row
            previous = session.execute(
                select(func.max(Chapter.chapter_index)).where(
                    Chapter.book_id == book_id, Chapter.chapter_index < chapter_index
                )
            ).scalar()
            following = session.execute(
                select(func.min(Chapter.chapter_index)).where(
                    Chapter.book_id == book_id, Chapter.chapter_index > chapter_index
                )
            ).scalar()
        return ChapterDetail(
            chapter_index=chapter.chapter_index,
            chapter_title=chapter.title,
            volume_index=volume_index,
            volume_title=volume_title,
            text=chapter.text,
            images=build_image_refs(book_id, chapter.image_paths),
            prev_chapter_index=previous,
            next_chapter_index=following,
        )


class EmptyCatalogRepository:
    def list_books(self) -> Sequence[BookSummary]:
        return ()

    def list_chapters(self, book_id: int) -> Sequence[ChapterSummary]:
        return ()

    def get_chapter(self, book_id: int, chapter_index: int) -> ChapterDetail | None:
        return None


__all__ = ["EmptyCatalogRepository", "PgCatalogRepository"]

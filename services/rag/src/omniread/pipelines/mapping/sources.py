"""映射的输入来源：把一章的正文与它的 chunk 正文取出来，还原成章内区间。

两条来源共用同一个还原函数（`spans_from_contents`），所以「语料直读」与「真库读取」
得到的区间只在数据本身不同时才不同——这让离线跑通的结论对真库也成立。

DB 模式读的是 `chapters.text` 与 `chunks.content`：两者都是当初导入写下的副本，
因此它验的是**冻结的那份切片**，不是「按当前代码重算应该是多少」。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from omniread.infrastructure.db.models import Chapter, Chunk
from omniread.infrastructure.objectstore.corpus import Corpus
from omniread.pipelines.chunking import chunk_chapter
from omniread.pipelines.mapping.spans import spans_from_contents
from omniread.pipelines.mapping.types import ChunkSpan


@dataclass(frozen=True, slots=True)
class ChapterSlices:
    """一章的正文与其 chunk 区间。"""

    chapter_id: str
    text: str
    spans: tuple[ChunkSpan, ...]


def slices_from_corpus(corpus: Corpus) -> dict[str, ChapterSlices]:
    """从仓库内语料直接分块；不连库，用于无水印环境下的全量验证。"""
    result: dict[str, ChapterSlices] = {}
    for chapter in corpus.chapters:
        drafts = chunk_chapter(chapter.chapter_id, chapter.text)
        result[chapter.chapter_id] = ChapterSlices(
            chapter_id=chapter.chapter_id,
            text=chapter.text,
            spans=tuple(spans_from_contents(
                chapter.chapter_id, chapter.text, [draft.content for draft in drafts]
            )),
        )
    return result


def slices_from_db(
    session_factory: sessionmaker[Session], book_id: int
) -> dict[str, ChapterSlices]:
    """从真库读冻结的章节正文与 chunk 正文，按 `chunk_index` 升序还原区间。"""
    with session_factory() as session:
        chapters = session.execute(
            select(Chapter.chapter_id, Chapter.text)
            .where(Chapter.book_id == book_id)
            .order_by(Chapter.chapter_index)
        ).all()
        rows = session.execute(
            select(Chunk.chapter_id, Chunk.chunk_index, Chunk.content)
            .where(Chunk.book_id == book_id)
            .order_by(Chunk.chapter_id, Chunk.chunk_index)
        ).all()

    contents: dict[str, list[str]] = {}
    for chapter_id, _chunk_index, content in rows:
        contents.setdefault(chapter_id, []).append(content)

    result: dict[str, ChapterSlices] = {}
    for chapter_id, text in chapters:
        chapter_contents = contents.get(chapter_id, [])
        result[chapter_id] = ChapterSlices(
            chapter_id=chapter_id,
            text=text,
            spans=tuple(spans_from_contents(chapter_id, text, chapter_contents)),
        )
    return result


def chapter_ids(slices: Mapping[str, ChapterSlices]) -> Iterable[str]:
    return slices.keys()

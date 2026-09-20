"""语料导入（M0-3）：`index.jsonl` → `books` / `volumes` / `chapters` / `chunks`。

职责边界（M0-02 §2、§3.3、§3.4）：

- 语料读取、P-3 最小规范化与逐章校验由 `omniread.infrastructure.objectstore.corpus.read_corpus`
  负责；缺字段、空正文在那里已是硬错误，导入不再静默跳过任何一行。
- 正文 hash 复用 `omniread.domain.text`，切片由 `omniread.pipelines.chunking` 产出，
  本模块只做「映射 → 落库 → prev/next 回填」。

落库口径：

- `books.id` M0 恒为 1（`--book-id` 可覆盖，用于测试库避开正式数据）。
- `volume_index` 取 `vol` 在语料中的首次出现次序，不按数字排——语料目录顺序不是阅读顺序。
- `chapter_index` 与 `index.jsonl` 行号严格 1:1。
- `chapters.image_paths` 原样取 `index.jsonl[].images`（保留语料自带的 `images/` 前缀），
  目录接口据此重建 `[插图NNN]` 的 marker→url 映射。
- `chunks.embedding` 留 NULL，由嵌入步骤另行回填；不写零向量占位。
- `chunking_version` / `tokenizer_id` 取自 profile 与 TokenCounter，与 chunk_key 同源冻结。

幂等：一次导入在单个事务里先删该书既有行、再整批写入，因此同一份语料重跑后行数、
`chunk_key`、`content_hash` 都不变。用整批替换而不是逐表 upsert：`volumes.id` 是自增且
不对外暴露（M0-02 §8.8），替换比 upsert 少一层「部分更新」的中间状态。

prev/next 在全部 chunk 落库后用一次窗口函数 UPDATE 统一回填：邻居由
`(chapter_id, chunk_index)` 排序决定，只可能落在同章，首块 prev / 末块 next 为 NULL。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, insert, text
from sqlalchemy.orm import Session

from omniread.infrastructure.db.models import Book, Chapter, Chunk, Volume
from omniread.infrastructure.objectstore.corpus import Corpus, CorpusFormatError, read_corpus
from omniread.infrastructure.tokenizer import TokenCounter, get_token_counter
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1, ChunkingProfile, chunk_chapter

# 全部 chunk 落库后统一回填 prev/next。PARTITION BY chapter_id 保证邻居只落在同章，
# 首块 prev / 末块 next 由 lag/lead 天然得到 NULL。别名避开与目标表同名的列。
_BACKFILL_NEIGHBORS_SQL = text(
    """
    WITH neighbors AS (
        SELECT
            chunk_key,
            lag(chunk_key) OVER (PARTITION BY chapter_id ORDER BY chunk_index) AS prev_key,
            lead(chunk_key) OVER (PARTITION BY chapter_id ORDER BY chunk_index) AS next_key
        FROM chunks
        WHERE book_id = :book_id
    )
    UPDATE chunks AS c
    SET prev_chunk_key = nb.prev_key,
        next_chunk_key = nb.next_key
    FROM neighbors AS nb
    WHERE c.chunk_key = nb.chunk_key
    """
)


@dataclass(frozen=True, slots=True)
class VolumePlan:
    volume_index: int
    title: str


@dataclass(frozen=True, slots=True)
class ChapterPlan:
    chapter_index: int
    chapter_id: str
    volume_index: int
    title: str
    source_id: str
    source_url: str
    text: str
    image_paths: tuple[str, ...]
    content_hash: str
    char_count: int


@dataclass(frozen=True, slots=True)
class ChunkPlan:
    chunk_key: str
    chapter_id: str
    chapter_index: int
    chunk_index: int
    content: str
    token_count: int
    content_hash: str
    chunking_version: str
    tokenizer_id: str


@dataclass(frozen=True, slots=True)
class ImportPlan:
    """一次导入要写入的全部行；不含 DB 自增 id，可离线构造与断言。"""

    book_id: int
    title: str
    author: str
    corpus_version: str
    volumes: tuple[VolumePlan, ...]
    chapters: tuple[ChapterPlan, ...]
    chunks: tuple[ChunkPlan, ...]


@dataclass(frozen=True, slots=True)
class ImportSummary:
    book_id: int
    volume_count: int
    chapter_count: int
    chunk_count: int

    def as_dict(self) -> dict[str, int]:
        return {
            "book_id": self.book_id,
            "volume_count": self.volume_count,
            "chapter_count": self.chapter_count,
            "chunk_count": self.chunk_count,
        }


def build_import_plan(
    corpus: Corpus,
    profile: ChunkingProfile = M0_PLACEHOLDER_V1,
    counter: TokenCounter | None = None,
) -> ImportPlan:
    """把读好的语料映射成待写入的行；纯函数，不碰数据库。"""
    used_counter = counter if counter is not None else get_token_counter()
    volume_indices = {
        title: index for index, title in enumerate(corpus.volume_titles, start=1)
    }
    volumes = tuple(
        VolumePlan(volume_index=index, title=title)
        for title, index in volume_indices.items()
    )

    chapters: list[ChapterPlan] = []
    chunks: list[ChunkPlan] = []
    for chapter in corpus.chapters:
        chapters.append(
            ChapterPlan(
                chapter_index=chapter.chapter_index,
                chapter_id=chapter.chapter_id,
                volume_index=volume_indices[chapter.volume_title],
                title=chapter.title,
                source_id=chapter.source_id,
                source_url=chapter.source_url,
                text=chapter.text,
                image_paths=chapter.image_paths,
                content_hash=chapter.content_hash,
                char_count=len(chapter.text),
            )
        )
        for draft in chunk_chapter(chapter.chapter_id, chapter.text, profile, used_counter):
            chunks.append(
                ChunkPlan(
                    chunk_key=draft.chunk_key,
                    chapter_id=chapter.chapter_id,
                    chapter_index=chapter.chapter_index,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    token_count=draft.token_count,
                    content_hash=draft.content_hash,
                    chunking_version=profile.profile_id,
                    tokenizer_id=profile.tokenizer_id,
                )
            )

    return ImportPlan(
        book_id=corpus.book_id,
        title=corpus.title,
        author=corpus.author,
        corpus_version=corpus.corpus_version,
        volumes=volumes,
        chapters=tuple(chapters),
        chunks=tuple(chunks),
    )


def write_import_plan(session: Session, plan: ImportPlan) -> ImportSummary:
    """在单个事务里删除该书既有行、写入计划、回填 prev/next，然后提交。"""
    book_id = plan.book_id
    _delete_book_rows(session, book_id)

    session.execute(
        insert(Book).values(
            id=book_id,
            title=plan.title,
            author=plan.author,
            corpus_version=plan.corpus_version,
        )
    )

    volume_ids: dict[int, int] = {}
    for volume in plan.volumes:
        volume_ids[volume.volume_index] = session.execute(
            insert(Volume)
            .values(book_id=book_id, volume_index=volume.volume_index, title=volume.title)
            .returning(Volume.id)
        ).scalar_one()

    if plan.chapters:
        session.execute(
            insert(Chapter),
            [
                {
                    "chapter_id": chapter.chapter_id,
                    "book_id": book_id,
                    "volume_id": volume_ids[chapter.volume_index],
                    "chapter_index": chapter.chapter_index,
                    "title": chapter.title,
                    "source_id": chapter.source_id,
                    "source_url": chapter.source_url,
                    "text": chapter.text,
                    "image_paths": list(chapter.image_paths),
                    "content_hash": chapter.content_hash,
                    "char_count": chapter.char_count,
                }
                for chapter in plan.chapters
            ],
        )

    if plan.chunks:
        # prev/next 先不写：等全部 chunk 落库后统一回填。
        session.execute(
            insert(Chunk),
            [
                {
                    "chunk_key": chunk.chunk_key,
                    "book_id": book_id,
                    "chapter_id": chunk.chapter_id,
                    "chapter_index": chunk.chapter_index,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_count": chunk.token_count,
                    "content_hash": chunk.content_hash,
                    "chunking_version": chunk.chunking_version,
                    "tokenizer_id": chunk.tokenizer_id,
                }
                for chunk in plan.chunks
            ],
        )
        session.execute(_BACKFILL_NEIGHBORS_SQL, {"book_id": book_id})

    session.commit()
    return ImportSummary(
        book_id=book_id,
        volume_count=len(plan.volumes),
        chapter_count=len(plan.chapters),
        chunk_count=len(plan.chunks),
    )


def _delete_book_rows(session: Session, book_id: int) -> None:
    """按外键依赖逆序删除该书全部行；重导即整批替换。"""
    session.execute(delete(Chunk).where(Chunk.book_id == book_id))
    session.execute(delete(Chapter).where(Chapter.book_id == book_id))
    session.execute(delete(Volume).where(Volume.book_id == book_id))
    session.execute(delete(Book).where(Book.id == book_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把语料 index.jsonl 导入 books/volumes/chapters/chunks（M0-02 §2）"
    )
    parser.add_argument("--corpus-root", required=True, type=Path, help="语料根目录")
    parser.add_argument("--book-id", type=int, default=1, help="书籍 ID，M0 恒为 1")
    parser.add_argument(
        "--corpus-version",
        default=None,
        help="语料版本；缺省时取 index.jsonl 字节 sha256 前 12 位",
    )
    args = parser.parse_args(argv)

    try:
        corpus = read_corpus(args.corpus_root, args.book_id, args.corpus_version)
    except CorpusFormatError as exc:
        print(f"语料不合法：{exc}", file=sys.stderr)
        return 2

    # 延迟导入：只在真正连库时构造引擎，语料错误不必先过凭据。
    from omniread.infrastructure.db.session import create_engine_from_env

    engine = create_engine_from_env()
    try:
        with Session(engine) as session:
            summary = write_import_plan(session, build_import_plan(corpus))
    finally:
        engine.dispose()

    # 直接写 UTF-8 字节：Windows 控制台默认 GBK，中文提示会变乱码。
    sys.stdout.buffer.write(
        (json.dumps(summary.as_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""领域模型：catalog 与查询请求的进程内表示，字段与契约 schema 一一对应。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RealmLevel(StrEnum):
    """`past` 只看 progress 之前的章；`full` 看全部章节。"""

    PAST = "past"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class ImageRef:
    marker: str
    url: str


@dataclass(frozen=True, slots=True)
class BookSummary:
    book_id: int
    title: str
    author: str
    chapter_count: int
    volume_count: int


@dataclass(frozen=True, slots=True)
class ChapterSummary:
    chapter_index: int
    chapter_title: str
    volume_index: int
    volume_title: str


@dataclass(frozen=True, slots=True)
class ChapterDetail:
    chapter_index: int
    chapter_title: str
    volume_index: int
    volume_title: str
    text: str
    images: tuple[ImageRef, ...]
    prev_chapter_index: int | None
    next_chapter_index: int | None


@dataclass(frozen=True, slots=True)
class QueryRequest:
    book_id: int
    question: str
    level: RealmLevel
    progress: int | None = None
    rewrite: bool = False
    neighbor_expand: bool = True


@dataclass(frozen=True, slots=True)
class ContextChapter:
    chapter_index: int
    chapter_title: str


@dataclass(frozen=True, slots=True)
class ContextChunk:
    """进入 prompt 的一段材料：正文 + 所属章标题。

    `chunk_key` 与 `context_assembled.chunks[]` 对齐，调用方据它把正文按装配顺序摆好；
    `chapter_title` 供 `context_chapters[]` 渲染角标，正文本身不带标题。
    """

    chunk_key: str
    chapter_index: int
    chapter_title: str
    text: str

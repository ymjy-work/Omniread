"""领域模型：catalog 与查询请求的进程内表示，字段与契约 schema 一一对应。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


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
class HistoryMessage:
    """一条历史对话消息。域内自己的类型，不引 infrastructure 的 `ChatMessage`——那会让
    领域层反过来依赖基础设施层。

    `frozen` 且字段都是不可变的，所以 `QueryRequest` 带着它仍然可哈希：
    评测的回放（`RecordedRetrieval`）拿 `QueryRequest` 当字典键，**塞一个 list 进去会当场
    TypeError**，而那是运行到评测那一半才炸。
    """

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class QueryRequest:
    book_id: int
    question: str
    level: RealmLevel
    progress: int | None = None
    rewrite: bool = True
    neighbor_expand: bool = True
    # 近轮对话原文，**不含本轮**，按时间升序；由 Java 按预算裁好再传。
    # 用 tuple 而不是 list：见 HistoryMessage 的注释（可哈希）。
    history: tuple[HistoryMessage, ...] = ()
    # 会话摘要，由 Java 维护并单独传，不占 history 的预算。
    # **没有摘要时是 None 而不是空串**：两者在 prompt 里该渲染成不同的东西
    # （空串会插出一条空的 system 消息）。
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class ContextChapter:
    chapter_index: int
    chapter_title: str


@dataclass(frozen=True, slots=True)
class ContextChunk:
    """进入 prompt 的一段材料：正文 + 所属章标题。

    `chunk_key` 与 `context_assembled.chunks[]` 对齐，调用方据它把正文按装配顺序摆好；
    `chapter_title` 供 `context_chapters[]` 渲染角标，正文本身不带标题。

    **与 `answering.prompt.ContextPassage` 是两个类型，不要合并**：这个是**跨层搬运**的形状
    （装配结果 → API → 调用方），所以多带 `chunk_key` 与 `chapter_title`；模型实际看到的
    只有「章号 + 正文」，渲染前转成 `ContextPassage`（转换点在 `application/query_service.py`）。
    合并会把两个内部字段漏进 prompt，而 prompt 版本跟着搬运格式一起变。
    """

    chunk_key: str
    chapter_index: int
    chapter_title: str
    text: str

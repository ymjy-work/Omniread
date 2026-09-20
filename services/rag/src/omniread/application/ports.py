"""应用层端口：外部依赖的抽象。infrastructure 提供实现，api 负责注入。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from omniread.domain.events import RagEvent
from omniread.domain.models import (
    BookSummary,
    ChapterDetail,
    ChapterSummary,
    ContextChunk,
    QueryRequest,
)
from omniread.pipelines.retrieval.types import RetrievalOutcome


@dataclass(frozen=True, slots=True)
class StoredObject:
    data: bytes
    content_type: str


class CatalogRepository(Protocol):
    """书籍 / 章节元数据与正文的来源。M0-2 接 PostgreSQL。"""

    def list_books(self) -> Sequence[BookSummary]: ...

    def list_chapters(self, book_id: int) -> Sequence[ChapterSummary]: ...

    def get_chapter(self, book_id: int, chapter_index: int) -> ChapterDetail | None: ...


class ImageStorage(Protocol):
    """插图二进制来源。key 形如 `books/{book_id}/images/{语料内相对路径}`。"""

    def get(self, key: str) -> StoredObject | None: ...


class RetrievalService(Protocol):
    """只跑检索链，产出逐阶段明细与最终装配集。

    `retrieval-only` 端点与离线评测 runner 走这里；问答路径（M0-5）在同一份
    `RetrievalOutcome` 之后接生成，不另起一条检索实现。
    """

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome: ...


class ContextSource(Protocol):
    """按装配集的 chunk_key 取回正文与章标题，供组装 prompt 与 `context_chapters`。

    `RetrievalOutcome.assembled` 只带 chunk_key / 章号 / 来源，正文不在其中（检索链
    用完即弃）；问答路径需要正文与标题，因此单独走这个只读入口。同步实现走 SQLAlchemy，
    调用方放进 `asyncio.to_thread`。
    """

    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]: ...


class QueryRunner(Protocol):
    """执行一次 RAG 问答，产出内部事件流。

    事件顺序与负载见 `omniread.domain.events`；成功以 `query_done` 收尾，
    失败以 `query_error` 收尾，两者互斥。
    """

    def run(self, request: QueryRequest, request_id: str) -> AsyncIterator[RagEvent]: ...

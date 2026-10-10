"""请求 / 响应模型，字段与契约 schema 逐项对应。

错误体只覆盖非 2xx；200 的 answered / insufficient_evidence 走各自的体，
不套用错误形状——拒答是正常业务结果。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from omniread.domain.errors import ErrorCode

REQUEST_ID_PATTERN = r"^req_[0-9a-f]{32}$"
_REQUEST_ID_FIELD = Field(pattern=REQUEST_ID_PATTERN)


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["omniread-rag", "omniread-backend"]


class Book(BaseModel):
    book_id: int
    title: str
    author: str
    chapter_count: int
    volume_count: int


class BookList(BaseModel):
    books: list[Book]


class ChapterSummaryBody(BaseModel):
    chapter_index: int
    chapter_title: str
    volume_index: int
    volume_title: str


class ChapterList(BaseModel):
    book_id: int
    chapters: list[ChapterSummaryBody]


class ImageRefBody(BaseModel):
    marker: str
    url: str


class ChapterDetail(BaseModel):
    chapter_index: int
    chapter_title: str
    volume_index: int
    volume_title: str
    text: str
    images: list[ImageRefBody]
    prev_chapter_index: int | None = None
    next_chapter_index: int | None = None


class QueryOptions(BaseModel):
    # 默认 true：多轮改造之后「有历史就消解指代」是常态（与内部契约的默认值一致）。
    # 真正决定改写跑不跑的是**有没有历史**——没有历史时 Python 自己落进 skipped、
    # 不发 rewrite_completed（契约 EventStream：有帧 ⟺ 真的跑了）。
    rewrite: bool = True
    neighbor_expand: bool = True


class QueryRequest(BaseModel):
    """两侧**共有**的那部分。`/rag/retrieval-only` 用的就是它，不带任何会话上下文。"""

    book_id: int
    question: str = Field(min_length=1, max_length=2000)
    level: Literal["past", "full"]
    progress: int | None = Field(default=None, ge=1, le=193)
    options: QueryOptions | None = None


class HistoryMessage(BaseModel):
    """一条历史对话消息。形状刻意比外部的 `ChatMessage` 窄——Python 不需要 id / seq。"""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class InternalQueryRequest(QueryRequest):
    """内部专有：共有核心 + Java 组装出来的上下文。

    **必须是显式字段**。pydantic 默认 `extra="ignore"`，所以少了这两个字段时
    对端发过来的 `history` / `summary` 会被**静默丢掉**——不报 400、日志里也没有痕迹，
    表现只是「多轮怎么不连贯」。填不满的字段不会自己喊。
    """

    history: list[HistoryMessage] | None = None
    summary: str | None = None


class ContextChapter(BaseModel):
    chapter_index: int
    chapter_title: str


class Usage(BaseModel):
    answer_provider: str
    answer_model: str
    latency_ms: int


class QueryResponse(BaseModel):
    request_id: str = _REQUEST_ID_FIELD
    status: Literal["answered", "insufficient_evidence"]
    answer: str
    context_chapters: list[ContextChapter]
    usage: Usage


class ErrorBody(BaseModel):
    request_id: str = _REQUEST_ID_FIELD
    code: ErrorCode
    message: str


class ScoredChunk(BaseModel):
    chunk_key: str
    chapter_index: int
    score: float
    rank: int


class AssembledChunk(BaseModel):
    chunk_key: str
    chapter_index: int
    source: Literal["hit", "neighbor"]


class DroppedChunk(BaseModel):
    chunk_key: str
    reason: str


class RealmBounds(BaseModel):
    lo: int
    hi: int


class RetrievalStages(BaseModel):
    dense: list[ScoredChunk]
    kw: list[ScoredChunk]
    fused: list[ScoredChunk]
    rerank: list[ScoredChunk]
    assembled: list[AssembledChunk]


class RetrievalOnlyResponse(BaseModel):
    request_id: str = _REQUEST_ID_FIELD
    realm: RealmBounds
    stages: RetrievalStages
    dropped: list[DroppedChunk] = []

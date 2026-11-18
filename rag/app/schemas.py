from typing import Literal

from pydantic import BaseModel, Field


class ChapterInput(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str
    text: str


class IndexRequest(BaseModel):
    book_id: int
    chapters: list[ChapterInput]


class IndexResponse(BaseModel):
    indexed_chunks: int


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    book_id: int
    question: str
    level: Literal["past", "full"]
    progress: int | None = None
    history: list[HistoryMessage] = Field(default_factory=list)
    top_k: int | None = None


class Citation(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str
    quote: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]

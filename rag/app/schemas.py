from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.rag.providers import PROVIDER_BASE_URLS


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
    mode: Literal["auto", "platform", "byok"] = "auto"
    provider: str | None = None
    model: str | None = None
    api_key: str | None = Field(default=None, repr=False)

    @field_validator("provider", "model")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("api_key")
    @classmethod
    def _normalize_api_key(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "AskRequest":
        if self.mode == "auto":
            if self.provider or self.model or self.api_key:
                raise ValueError(
                    "auto mode does not accept provider, model or api_key"
                )
            return self

        if self.mode == "platform":
            if self.provider is None:
                self.provider = "bailian"
            if self.provider != "bailian":
                raise ValueError("platform mode only supports provider 'bailian'")
            if self.model is None:
                raise ValueError("platform mode requires model")
            if self.api_key is not None:
                raise ValueError("platform mode does not accept api_key")
            return self

        if self.provider is None:
            raise ValueError("byok mode requires provider")
        if self.provider not in PROVIDER_BASE_URLS:
            raise ValueError("byok mode provider is not supported")
        if self.model is None:
            raise ValueError("byok mode requires model")
        if self.api_key is None:
            raise ValueError("byok mode requires api_key")
        return self


class Citation(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str
    quote: str


class AskUsage(BaseModel):
    mode: Literal["auto", "platform", "byok"]
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    usage: AskUsage
"""模型 provider 接口（M0-01 §5.1）：回答 / embedding / rerank。

核心业务只依赖这三个接口，协议转换由适配器负责（`ali.py` 的 embedding 与 rerank，
回答模型随 M0-5 落地）。调用一律异步——适配器走 `httpx.AsyncClient`，与 FastAPI 的
请求生命周期一致。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

# 回答模型可见的角色集合，与 OpenAI 风格消息一致。
ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class ChatOptions:
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """一次非流式补全的结果。`reasoning` 与 `text` 分开存：用户回答只用 `text`。"""

    text: str
    model: str
    reasoning: str | None = None


@dataclass(frozen=True, slots=True)
class ChatChunk:
    """流式分片；`text` 是增量正文，不含 reasoning 内容。"""

    text: str


@dataclass(frozen=True, slots=True)
class RerankResult:
    """一条重排结果。

    `index` 是**入参 documents 的下标**，不是 chunk 标识——适配器不接触 chunk_key，
    由调用方按下标回填。结果按 `score` 降序、`index` 升序排列。
    """

    index: int
    score: float


@runtime_checkable
class ChatModel(Protocol):
    """回答模型。"""

    model: str

    async def complete(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> ChatResponse: ...

    def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]: ...


@runtime_checkable
class EmbeddingModel(Protocol):
    """向量模型。`dim` 必须与 `chunks.embedding` 的列维度一致（1024）。"""

    model: str
    dim: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class RerankModel(Protocol):
    """重排模型。`top_n` 缺省表示返回全部入参文档。"""

    model: str

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int | None = None
    ) -> list[RerankResult]: ...

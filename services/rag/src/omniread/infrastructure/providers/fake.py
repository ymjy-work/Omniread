"""确定性假 provider：本轮所有检索与回答测试用它，替代真实 API 调用。

用途：单元测试、装配与融合的离线验证、评测 runner 的自检。它**不是**降级实现——
线上路径永远走真实适配器；假 provider 只在测试与离线脚本里显式注入。

确定性由 sha 派生或固定配置保证：同一输入永远得到同一输出，不依赖随机数、进程、时间或
`hash()`（后者按进程加盐，跨进程不可复现）。假向量只保证「同文本同向量、异文本
几乎必不同」，不承载任何语义——需要真实相关性时用真实 embedding 模型。
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import AsyncIterator, Sequence

from omniread.infrastructure.providers.base import (
    ChatChunk,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    RerankResult,
)
from omniread.infrastructure.providers.errors import ProviderError, ProviderTimeoutError

# 伪向量的域分隔前缀：与真模型输出无关，只用于把派生输入与其它 sha 用途区分开。
_EMBEDDING_DOMAIN = "omniread-fake-embedding-v1"
_RERANK_DOMAIN = "omniread-fake-rerank-v1"

_DIGEST_BYTES_PER_COMPONENT = 4


def _pseudo_vector(text: str, dim: int) -> list[float]:
    """由文本 sha 派生 dim 维单位向量。

    `shake_256` 是 XOF：一次摘要就能取够 `dim * 4` 字节，不必逐分量再哈希。
    分量映射到 [-1, 1) 后做 L2 归一化——余弦距离下只有方向有意义，单位向量让
    「同文本距离为 0」成立。
    """
    digest = hashlib.shake_256(f"{_EMBEDDING_DOMAIN}\n{text}".encode()).digest(
        dim * _DIGEST_BYTES_PER_COMPONENT
    )
    values = [
        int.from_bytes(
            digest[i * _DIGEST_BYTES_PER_COMPONENT : (i + 1) * _DIGEST_BYTES_PER_COMPONENT], "big"
        )
        / 2**31
        - 1.0
        for i in range(dim)
    ]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _pseudo_score(query: str, document: str) -> float:
    """由 (query, document) 派生的确定性分数，落在 [0, 1)。"""
    digest = hashlib.sha256(f"{_RERANK_DOMAIN}\n{query}\n{document}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class FakeEmbeddingModel:
    """确定性 embedding：向量由文本 sha 派生，无网络、无随机。"""

    def __init__(self, dim: int = 1024, model: str = "fake-embedding") -> None:
        self.dim = dim
        self.model = model

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [_pseudo_vector(text, self.dim) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return _pseudo_vector(text, self.dim)


class FakeRerankModel:
    """确定性 rerank：分数由 (query, document) 的 sha 派生。

    分数与文本语义无关，只用于「同一输入两次运行结果一致」的验证；`RerankResult.index`
    是入参 documents 的下标，排序规则与真实适配器一致（分数降序、下标升序）。
    """

    def __init__(self, model: str = "fake-rerank") -> None:
        self.model = model

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int | None = None
    ) -> list[RerankResult]:
        ranked = sorted(
            (RerankResult(index=index, score=_pseudo_score(query, document))
             for index, document in enumerate(documents)),
            key=lambda result: (-result.score, result.index),
        )
        if top_n is None:
            return ranked
        return ranked[:top_n]


class FakeChatModel:
    """确定性假回答模型：无网络、无随机，两次运行产出一致。

    `complete` 返回配置的固定正文；`stream` 按固定 `chunk_size` 切片逐块 yield，切片序列
    只由正文决定。`reasoning` 只在非流式响应里携带，用来验证调用方只取 `text`。
    入参消息记录在 `calls` 里，供测试确认送进模型的 prompt。
    """

    def __init__(
        self,
        *,
        # 默认正文带一条规范引用 `[C1]`：全栈联调时回答固定，浏览器端才有可点角标可验证，
        # 端到端「流式回答 → 引用跳章」不必依赖真实 provider。真 provider 输出不受影响。
        answer: str = "这是假 provider 的回答，依据材料 [C1]。",
        reasoning: str | None = None,
        chunk_size: int = 4,
        delay_ms: int = 0,
        model: str = "fake-chat",
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须为正整数")
        if delay_ms < 0:
            raise ValueError("delay_ms 不能为负")
        self.model = model
        self._answer = answer
        self._reasoning = reasoning
        self._chunk_size = chunk_size
        self._delay_ms = delay_ms
        self.calls: list[tuple[ChatMessage, ...]] = []

    async def complete(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> ChatResponse:
        self.calls.append(tuple(messages))
        return ChatResponse(text=self._answer, model=self.model, reasoning=self._reasoning)

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        self.calls.append(tuple(messages))
        for start in range(0, len(self._answer), self._chunk_size):
            if self._delay_ms > 0:
                await asyncio.sleep(self._delay_ms / 1000)
            yield ChatChunk(text=self._answer[start : start + self._chunk_size])


class FaultyChatModel:
    """故障注入假回答模型：按模式抛 provider 错误，验证 5xx 映射。

    只用于联调/测试：让真实的 Python 服务在生成阶段抛出 provider 故障，从而产出
    502 `RAG_PROVIDER_ERROR` / 504 `RAG_TIMEOUT`，Java 网关的上游错误映射才有真实对手。
    """

    def __init__(self, fault: str, *, model: str = "fake-chat-fault") -> None:
        if fault not in ("provider_error", "timeout"):
            raise ValueError("fault 只能是 provider_error 或 timeout")
        self.model = model
        self._fault = fault

    def _raise(self) -> None:
        if self._fault == "timeout":
            raise ProviderTimeoutError("假 provider 注入的超时", provider="fake")
        raise ProviderError("假 provider 注入的错误", provider="fake")

    async def complete(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> ChatResponse:
        self._raise()
        raise AssertionError("unreachable")  # pragma: no cover

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        self._raise()
        yield ChatChunk(text="")  # pragma: no cover - 协程转生成器，_raise 先于首块执行

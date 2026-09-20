"""问答用例：检索 → 装配 → prompt → 流式生成 → 引用 → 内部事件流。

`AnsweringRunner` 是问答链的唯一编排点，只产出 `domain.events` 定义的事件；JSON / SSE
适配器负责把同一条流编码成网络格式，不含业务逻辑。事件顺序与负载见 M0-02 §8.5。

几条口径在代码里的落点：

- **服务端不改写模型输出**：`chunk.text` 原样进 `answer_delta`，不做引用白名单过滤、也不
  剔除越界引用（M0-04 §4：半成品防护只覆盖「带越界引用的越界」，覆盖不了「不带引用的
  越界」，还会制造「已经防住了」的错觉）。越界引用由评测的 `answer_citation_membership`
  计为失败。
- **拒答判据是最终装配集为空**（`context_assembled.chunks[]` 为空）。M0 不做模型级拒答
  的结构化标记（M0-02 §8.3），「有证据但模型答不出」交由生成层 judge 判定，因此这是
  唯一的确定性判据。拒答时 `answer` 由服务端固定话术填充，不走模型。
- **provider 故障不降级成拒答**：检索或生成阶段抛出的 `ProviderError` 一律映射成
  `query_error`（超时 `RAG_TIMEOUT`、其余 `RAG_PROVIDER_ERROR`），由适配器写成 5xx；
  故障与「材料不足」不互相伪装。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from omniread.application.ports import ContextSource, RetrievalService
from omniread.domain.errors import ErrorCode, RagError, RagUnavailable
from omniread.domain.events import (
    AnswerStatus,
    RagEvent,
    answer_delta,
    citation_ready,
    context_assembled,
    generation_started,
    query_done,
    query_error,
    query_started,
    realm_resolved,
    rerank_completed,
    retrieval_completed,
)
from omniread.domain.models import ContextChunk, QueryRequest
from omniread.infrastructure.providers.base import ChatModel
from omniread.infrastructure.providers.errors import ProviderError, to_rag_error
from omniread.pipelines.answering.prompt import (
    AnswerPrompt,
    ContextPassage,
    answer_prompt_version,
    build_answer_messages,
)
from omniread.pipelines.retrieval.types import RetrievalOutcome

logger = logging.getLogger(__name__)

# 中间事件的 top 列表截断：契约 §8.5 的 `fused_top[]` / `ranked[]` 都是 ≤10。
_EVENT_TOP = 10

# 拒答话术：服务端固定文本，取自 M0-02 §8.3 的示例。它不是模型输出，模型在拒答路径上
# 根本不被调用——避免模型在拒答话术里夹带域外信息。
REFUSAL_ANSWER = "当前进度内的文本里没有找到能回答这个问题的内容。"


class UnimplementedQueryRunner:
    """问答链未接线时的兜底 runner：不发任何业务事件，只以 `query_error` 收尾。

    JSON 适配器会把它折叠成契约错误体（503），SSE 适配器会编码成
    `event: error` 帧后关闭连接。
    """

    def __init__(self, message: str = "RAG 管线未实现") -> None:
        self._message = message

    async def run(self, request: QueryRequest, request_id: str) -> AsyncIterator[RagEvent]:
        yield query_error(
            request_id=request_id,
            code=ErrorCode.RAG_UNAVAILABLE.value,
            message=self._message,
        )


class AnsweringRunner:
    """把检索链、装配上下文、回答模型接成一条事件流。"""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        context: ContextSource,
        chat: ChatModel,
        answer_provider: str = "glm",
        prompt: AnswerPrompt | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._context = context
        self._chat = chat
        self._answer_provider = answer_provider
        self._prompt = prompt

    async def run(self, request: QueryRequest, request_id: str) -> AsyncIterator[RagEvent]:
        started = time.perf_counter()
        yield query_started(
            request_id=request_id,
            book_id=request.book_id,
            level=request.level.value,
            progress=request.progress,
        )
        try:
            async for event in self._run_body(request, started):
                yield event
        except ProviderError as exc:
            # 超时 / 熔断 / 响应错误：502 或 504，绝不退化成 insufficient_evidence。
            error = to_rag_error(exc)
            logger.warning("回答链 provider 故障 request=%s code=%s", request_id, error.code)
            yield query_error(
                request_id=request_id, code=error.code.value, message=error.message
            )
        except RagError as exc:
            yield query_error(
                request_id=request_id, code=exc.code.value, message=exc.message
            )
        except SQLAlchemyError as exc:
            logger.warning("回答链数据库不可用 request=%s：%s", request_id, exc)
            yield query_error(
                request_id=request_id,
                code=ErrorCode.RAG_UNAVAILABLE.value,
                message="检索库不可用",
            )

    async def _run_body(
        self, request: QueryRequest, started: float
    ) -> AsyncIterator[RagEvent]:
        outcome = await self._retrieval.retrieve(request)
        yield realm_resolved(lo=outcome.realm.lo, hi=outcome.realm.hi)
        yield retrieval_completed(
            dense_count=len(outcome.dense),
            bm25_count=len(outcome.kw),
            fused_count=len(outcome.fused),
            fused_top=[
                {"chunk_key": hit.chunk_key} for hit in outcome.fused[:_EVENT_TOP]
            ],
        )
        yield rerank_completed(
            input_count=min(len(outcome.fused), outcome.params.rerank_k),
            output_count=len(outcome.reranked),
            ranked=[
                {"chunk_key": hit.chunk_key, "score": hit.score}
                for hit in outcome.reranked[:_EVENT_TOP]
            ],
        )
        yield context_assembled(
            chunks=[
                {
                    "chunk_key": item.chunk_key,
                    "chapter_index": item.chapter_index,
                    "source": item.source,
                }
                for item in outcome.assembled
            ],
            token_estimate=outcome.token_estimate,
            dropped=[
                {"chunk_key": item.chunk_key, "reason": item.reason}
                for item in outcome.dropped
            ],
        )

        chunks = await self._load_context(request.book_id, outcome)
        context_chapters = _context_chapters(chunks)
        yield generation_started(
            answer_provider=self._answer_provider,
            answer_model=self._chat.model,
            prompt_version=answer_prompt_version(),
        )

        if not chunks:
            # 证据不足：固定话术走同一条 generation_started → answer_delta 形状，适配器
            # 因此不需要任何拒答分支；context_chapters 此时恒为 []（检索为空导致的拒答）。
            yield answer_delta(text=REFUSAL_ANSWER)
            yield citation_ready(context_chapters=[])
            yield query_done(
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                context_chapters=[],
                usage=self._usage(started),
            )
            return

        passages = [
            ContextPassage(chapter_index=chunk.chapter_index, text=chunk.text)
            for chunk in chunks
        ]
        messages = build_answer_messages(
            request.question, passages, prompt=self._prompt
        )
        async for chunk in self._chat.stream(messages):
            if chunk.text:
                yield answer_delta(text=chunk.text)

        yield citation_ready(context_chapters=context_chapters)
        yield query_done(
            status=AnswerStatus.ANSWERED,
            context_chapters=context_chapters,
            usage=self._usage(started),
        )

    async def _load_context(
        self, book_id: int, outcome: RetrievalOutcome
    ) -> list[ContextChunk]:
        """按装配顺序取回正文；缺正文说明库与检索视图不一致，显式失败而不是当空上下文。"""
        keys = [item.chunk_key for item in outcome.assembled]
        if not keys:
            return []
        loaded = await asyncio.to_thread(self._context.load, book_id, keys)
        by_key = {chunk.chunk_key: chunk for chunk in loaded}
        missing = [key for key in keys if key not in by_key]
        if missing:
            raise RagUnavailable(f"装配上下文缺少 {len(missing)} 个 chunk 正文")
        return [by_key[item.chunk_key] for item in outcome.assembled]

    def _usage(self, started: float) -> dict[str, Any]:
        return {
            "answer_provider": self._answer_provider,
            "answer_model": self._chat.model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


def _context_chapters(chunks: Sequence[ContextChunk]) -> list[dict[str, Any]]:
    """装配集涉及的章去重，按 `chapter_index` 升序；标题取该章任一 chunk 携带的值。"""
    titles: dict[int, str] = {}
    for chunk in chunks:
        titles.setdefault(chunk.chapter_index, chunk.chapter_title)
    return [
        {"chapter_index": chapter_index, "chapter_title": titles[chapter_index]}
        for chapter_index in sorted(titles)
    ]


__all__ = ["REFUSAL_ANSWER", "AnsweringRunner", "UnimplementedQueryRunner"]

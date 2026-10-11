"""rag 路由：同步 JSON、SSE 事件流、只跑检索（评测用）。

两条问答路径用**路径**区分而不是 Accept 内容协商：适配器选择是显式的，省掉协商分支与
Accept 解析的边界情况。三条路径共用同一份内部事件流，只是编码方式不同。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from omniread.api import schemas
from omniread.api.adapters import JsonResponseAdapter, SseResponseAdapter
from omniread.api.deps import get_query_runner, get_retrieval, get_summarizer, request_id_of
from omniread.application.ports import QueryRunner, RetrievalService
from omniread.domain.errors import RagUnavailable
from omniread.domain.models import HistoryMessage, QueryRequest, RealmLevel
from omniread.infrastructure.providers.errors import ProviderError, to_rag_error
from omniread.pipelines.retrieval.types import RetrievalOutcome, StageHit
from omniread.pipelines.summarizing import SessionSummarizer

router = APIRouter(tags=["rag"])

_PROVIDER_ERRORS: dict[int | str, dict[str, Any]] = {
    502: {"model": schemas.ErrorBody, "description": "provider 返回错误"},
    # 未接线（缺库凭据 / provider 凭据）。**它不是降级路径**：端点显式 503，
    # 比让整进程起不来更便于运维定位。
    503: {"model": schemas.ErrorBody, "description": "服务未接线（缺凭据或库）"},
    504: {"model": schemas.ErrorBody, "description": "provider 超时"},
}


def _to_domain(payload: schemas.QueryRequest) -> QueryRequest:
    options = payload.options or schemas.QueryOptions()
    return QueryRequest(
        book_id=payload.book_id,
        question=payload.question,
        level=RealmLevel(payload.level),
        progress=payload.progress,
        rewrite=options.rewrite,
        neighbor_expand=options.neighbor_expand,
    )


def _with_context(request: QueryRequest, payload: schemas.InternalQueryRequest) -> QueryRequest:
    """把 Java 组装好的上下文并进来。

    只有两条**问答**路径走这里。`/rag/retrieval-only` 用的仍然是不带上下文的共享
    `QueryRequest`（契约里那一条路径的请求体就是它）——评测跑的是单轮，不该被会话状态污染。
    """
    return replace(
        request,
        history=tuple(
            HistoryMessage(role=message.role, content=message.content)
            for message in (payload.history or ())
        ),
        summary=payload.summary,
    )


@router.post(
    "/rag/query",
    response_model=schemas.QueryResponse,
    operation_id="internalRagQuery",
    responses=_PROVIDER_ERRORS,
)
async def rag_query(
    payload: schemas.InternalQueryRequest,
    request: Request,
    runner: QueryRunner = Depends(get_query_runner),
) -> schemas.QueryResponse:
    request_id = request_id_of(request)
    return await JsonResponseAdapter.fold(
        runner.run(_with_context(_to_domain(payload), payload), request_id),
        request_id=request_id,
    )


@router.post(
    "/rag/query-stream",
    operation_id="internalRagQueryStream",
    responses={
        200: {
            "description": "SSE 帧流",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def rag_query_stream(
    payload: schemas.InternalQueryRequest,
    request: Request,
    runner: QueryRunner = Depends(get_query_runner),
) -> StreamingResponse:
    request_id = request_id_of(request)
    frames = SseResponseAdapter.stream(
        runner.run(_with_context(_to_domain(payload), payload), request_id),
        request_id=request_id,
    )
    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def _scored_chunks(hits: tuple[StageHit, ...]) -> list[schemas.ScoredChunk]:
    return [
        schemas.ScoredChunk(
            chunk_key=hit.chunk_key,
            chapter_index=hit.chapter_index,
            score=hit.score,
            rank=hit.rank,
        )
        for hit in hits
    ]


def _retrieval_response(
    outcome: RetrievalOutcome, request_id: str
) -> schemas.RetrievalOnlyResponse:
    """逐阶段完整、不截断（M0-02 §8.7）；装配集按 `chunk_index` 升序呈现。"""
    return schemas.RetrievalOnlyResponse(
        request_id=request_id,
        realm=schemas.RealmBounds(lo=outcome.realm.lo, hi=outcome.realm.hi),
        stages=schemas.RetrievalStages(
            dense=_scored_chunks(outcome.dense),
            kw=_scored_chunks(outcome.kw),
            fused=_scored_chunks(outcome.fused),
            rerank=_scored_chunks(outcome.reranked),
            assembled=[
                schemas.AssembledChunk(
                    chunk_key=item.chunk_key,
                    chapter_index=item.chapter_index,
                    source=item.source,
                )
                for item in outcome.assembled
            ],
        ),
        dropped=[
            schemas.DroppedChunk(chunk_key=item.chunk_key, reason=item.reason)
            for item in outcome.dropped
        ],
    )


@router.post(
    "/rag/retrieval-only",
    response_model=schemas.RetrievalOnlyResponse,
    operation_id="internalRagRetrievalOnly",
    responses=_PROVIDER_ERRORS,
)
async def rag_retrieval_only(
    payload: schemas.QueryRequest,
    request: Request,
    service: RetrievalService = Depends(get_retrieval),
) -> schemas.RetrievalOnlyResponse:
    request_id = request_id_of(request)
    try:
        outcome = await service.retrieve(_to_domain(payload))
    except ProviderError as exc:
        # provider 故障不降级为拒答：超时 504、其余 502。
        raise to_rag_error(exc) from exc
    except SQLAlchemyError as exc:
        raise RagUnavailable("检索库不可用") from exc
    return _retrieval_response(outcome, request_id)


@router.post(
    "/summarize",
    response_model=schemas.SummarizeResponse,
    operation_id="internalSummarize",
    responses=_PROVIDER_ERRORS,
)
async def summarize(
    payload: schemas.SummarizeRequest,
    summarizer: SessionSummarizer = Depends(get_summarizer),
) -> schemas.SummarizeResponse:
    """会话摘要。由 Java 在后台按阈值触发，**不在用户请求链路上**。

    `request_id` 照常由中间件放进上下文（错误体要带它），这里不需要再取一次。

    失败一律往上抛：provider 故障 502 / 超时 504 / 没接线 503。**Java 收到失败就什么都不动**
    ——不推进 `summary_upto`，下次可重试且不会重复压缩。
    """
    try:
        summary, prompt_version = await summarizer.summarize(
            payload.previous_summary,
            [
                HistoryMessage(role=message.role, content=message.content)
                for message in payload.messages
            ],
        )
    except ProviderError as exc:
        # provider 故障不降级：超时 504、其余 502。**必须显式转换**——
        # `ProviderError` 不是 `RagError`，让它自己冒上去会落到兜底处理器变成 503，
        # 而契约给这条路径声明的是 502 / 504（与另外三条 rag 路径同一条口径）。
        raise to_rag_error(exc) from exc
    return schemas.SummarizeResponse(summary=summary, prompt_version=prompt_version)

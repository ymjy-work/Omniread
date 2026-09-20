"""事件流适配器：把同一条内部事件流编码成 JSON 对象或 SSE 帧。

适配器不含业务逻辑——「发生了什么」由 `domain.events` 定义，「怎么编码成网络格式」
只在这里决定。两个适配器共用同一份事件流，行为只定义一次，因此不需要两套测试与两处修
bug。中间事件（realm / 检索 / 重排 / 装配 / generation_started）不参与 JSON 折叠，
它们的消费者是失败定位与 SSE 前端。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from omniread.api.schemas import ErrorBody, QueryResponse
from omniread.domain.errors import RagError, RagUnavailable, error_from_wire
from omniread.domain.events import EventName, RagEvent

# 成功 SSE 流的终止帧；异常流不发本帧，改发 ERROR_EVENT。
DONE_FRAME = "data: [DONE]\n\n"

# SSE 层的错误事件名。内部终态事件 query_error / query_done 分别编码成本事件与 [DONE]，
# 不直接把 query_error 当事件名下发——契约规定客户端只需认 `error` 与 `[DONE]` 两个终止信号。
ERROR_EVENT = "error"


def encode_frame(event: str, data: Mapping[str, Any] | list[Any]) -> str:
    """一帧 = `event:` 行 + 单行 `data:` 行 + 空行。

    `json.dumps` 会把正文里的换行转义成 `\\n`，保证 data 只有一行；不转义会让一帧被
    客户端切成两帧，正文里的换行也就能伪造事件边界。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_payload(payload: Mapping[str, Any], request_id: str) -> dict[str, Any]:
    error = error_from_wire(str(payload.get("code", "")), str(payload.get("message", "")))
    return _body(request_id=payload.get("request_id") or request_id, error=error)


def _body(*, request_id: Any, error: RagError) -> dict[str, Any]:
    return ErrorBody(request_id=request_id, code=error.code, message=error.message).model_dump(
        mode="json"
    )


class JsonResponseAdapter:
    """把事件流折叠成单个 JSON 对象（契约 QueryResponse）。

    失败时抛出具 HTTP 状态码的领域异常，由异常处理器写成统一错误体。
    """

    @staticmethod
    async def fold(events: AsyncIterator[RagEvent], *, request_id: str) -> QueryResponse:
        answer_parts: list[str] = []
        context_chapters: list[dict[str, Any]] = []
        status: str | None = None
        usage: dict[str, Any] | None = None

        async for event in events:
            if event.name is EventName.ANSWER_DELTA:
                answer_parts.append(str(event.payload["text"]))
            elif event.name is EventName.CITATION_READY:
                context_chapters = list(event.payload["context_chapters"])
            elif event.name is EventName.QUERY_DONE:
                status = str(event.payload["status"])
                context_chapters = list(event.payload["context_chapters"])
                usage = dict(event.payload["usage"])
            elif event.name is EventName.QUERY_ERROR:
                raise error_from_wire(
                    str(event.payload["code"]), str(event.payload["message"])
                )

        if status is None or usage is None:
            raise RagUnavailable("事件流未以 query_done 收尾")

        return QueryResponse.model_validate(
            {
                "request_id": request_id,
                "status": status,
                "answer": "".join(answer_parts),
                "context_chapters": context_chapters,
                "usage": usage,
            }
        )


class SseResponseAdapter:
    """把事件流逐条编码为 SSE 帧。

    终止规则：query_done → 本帧 + `data: [DONE]`；query_error 或流内抛出的领域异常 →
    `event: error` + 错误体，然后关连接，不再发 `[DONE]`。两者互斥。
    """

    @staticmethod
    async def stream(
        events: AsyncIterator[RagEvent], *, request_id: str
    ) -> AsyncIterator[str]:
        try:
            async for event in events:
                if event.name is EventName.QUERY_ERROR:
                    yield encode_frame(ERROR_EVENT, _error_payload(event.payload, request_id))
                    return
                yield encode_frame(event.name.value, event.payload)
                if event.name is EventName.QUERY_DONE:
                    yield DONE_FRAME
                    return
        except RagError as exc:
            yield encode_frame(ERROR_EVENT, _body(request_id=request_id, error=exc))
            return
        except Exception:
            error = RagUnavailable("RAG 服务内部错误")
            yield encode_frame(ERROR_EVENT, _body(request_id=request_id, error=error))
            return

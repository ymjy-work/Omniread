"""错误体的唯一构造点与异常处理器。

统一错误体 `{request_id, code, message}` 三字段扁平、`application/json`、只覆盖非 2xx。
HTTP 状态码是权威判别位；`message` 由各领域异常给定，不含路径 / 堆栈 / provider 原始体。
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from omniread.api.deps import request_id_of
from omniread.api.schemas import ErrorBody
from omniread.domain.errors import RagError, RagInvalidRealm, RagUnavailable

logger = logging.getLogger(__name__)


def error_response(request: Request, error: RagError) -> JSONResponse:
    body = ErrorBody(
        request_id=request_id_of(request),
        code=error.code,
        message=error.message,
    )
    return JSONResponse(status_code=error.http_status, content=body.model_dump(mode="json"))


async def handle_rag_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RagError)
    if isinstance(exc, RagUnavailable):
        # 未接线的检索 / 问答链与内部故障都归 503；这条日志是运维判断服务是否可用的依据。
        logger.warning("返回 503：%s", exc.message)
    return error_response(request, exc)


async def handle_request_validation_error(
    request: Request, exc: Exception
) -> JSONResponse:
    """入参校验失败按 RAG_INVALID_REALM / 400 返回，而不是 FastAPI 默认的 422。

    对外只暴露一类错误体；具体哪个字段不合法不回传，避免把内部模型结构写进 message。
    """
    assert isinstance(exc, RequestValidationError)
    return error_response(request, RagInvalidRealm("请求体或路径参数不合法"))


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """兜底：未预期异常也只回统一错误体，message 固定，不带堆栈。"""
    return error_response(request, RagUnavailable("RAG 服务内部错误"))

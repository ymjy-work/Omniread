"""请求作用域的依赖：request_id 解析与端口注入。

`X-Request-Id` 由 Java 生成并透传，白名单直连（retrieval-only、评测 runner）时由本服务
入口生成。取值带格式约束（`req_` + 32 位小写十六进制），不合格式的一律当没传——
外部给的字符串不能直接进响应体与日志。
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from omniread.application.ports import (
    CatalogRepository,
    ImageStorage,
    QueryRunner,
    RetrievalService,
)
from omniread.config import Settings
from omniread.domain.errors import RagUnavailable
from omniread.logging_config import bind_request_id

logger = logging.getLogger(__name__)

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")

REQUEST_ID_HEADER = "X-Request-Id"


def new_request_id() -> str:
    return f"req_{secrets.token_hex(16)}"


def sanitize_request_id(candidate: str | None) -> str:
    if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_request_id()


def request_id_of(request: Request) -> str:
    """优先取中间件写入的 state；直接调用处理器（如单测）时回落到 header。"""
    from_state = getattr(request.state, "request_id", None)
    if isinstance(from_state, str) and from_state:
        return from_state
    return sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))


async def attach_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """解析 request_id：写进请求 state、绑定日志上下文，再放行。

    本次请求后续的所有日志（含异常处理器里的）都带上同一个 id。
    """
    request_id = sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    bind_request_id(request_id)
    logger.info("请求进入 %s %s", request.method, request.url.path)
    return await call_next(request)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_catalog(request: Request) -> CatalogRepository:
    return request.app.state.catalog


def get_image_storage(request: Request) -> ImageStorage:
    return request.app.state.image_storage


def get_query_runner(request: Request) -> QueryRunner:
    return request.app.state.query_runner


def get_retrieval(request: Request) -> RetrievalService:
    """检索链未接线（缺库凭据或 provider 凭据）时显式 503，不静默降级成空结果。"""
    service = getattr(request.app.state, "retrieval", None)
    if service is None:
        raise RagUnavailable("检索链未接线：缺数据库或 provider 配置")
    return service

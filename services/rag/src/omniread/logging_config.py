"""日志装配与 request_id 日志上下文。

`OMNIREAD_LOG_LEVEL`（见 config.py）是唯一的级别来源。配置动作只在 `create_app`
里发生，不在导入时产生副作用——导入即改全局 logging 状态会让应用实例之间互相污染。

每条日志都带 `request_id`：中间件在请求入口把它写进 contextvar，`RequestIdFilter`
再注入 LogRecord。contextvar 按 asyncio 任务隔离，并发请求不会串号。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

LOGGER_NAME = "omniread"

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s"

_request_id_var: ContextVar[str | None] = ContextVar("omniread_request_id", default=None)


def bind_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def current_request_id() -> str | None:
    return _request_id_var.get()


class RequestIdFilter(logging.Filter):
    """把 contextvar 里的 request_id 注入每条 LogRecord。

    无关请求的进程级日志（启动、后台任务）没有绑定值，记 `-` 而不是省略字段，
    格式因此恒定，日志采集端不需要处理两种行形状。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        return True


class _ServiceHandler(logging.StreamHandler):
    """标记为本服务自己装配的 handler：重复配置时只替换自己加的那个，
    外部（测试、宿主进程）挂到本命名空间上的 handler 不受影响。"""


def configure_logging(level: str) -> None:
    """按配置装配 `omniread` 命名空间的日志，重复调用幂等。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    # 只由本服务自己的 handler 输出：向 root 传播会在 uvicorn 等已配置 root 的场景下重复打印。
    logger.propagate = False
    for handler in list(logger.handlers):
        if isinstance(handler, _ServiceHandler):
            logger.removeHandler(handler)

    handler = _ServiceHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)

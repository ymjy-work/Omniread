"""日志：级别由 settings.log_level 决定，request_id 出现在每条记录里。"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from helpers import REQUEST_ID
from omniread.api.app import create_app
from omniread.config import Settings
from omniread.infrastructure.db.catalog import EmptyCatalogRepository
from omniread.logging_config import LOGGER_NAME, RequestIdFilter

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")

QUERY_BODY = {
    "book_id": 1,
    "question": "政近为什么离开周防家？",
    "level": "past",
    "progress": 45,
}


class _CaptureHandler(logging.Handler):
    """挂到 `omniread` 命名空间上的记录收集器。

    带 `RequestIdFilter` 以复现真实注入；测试自己的 handler 不属于服务装配的
    `_ServiceHandler`，`configure_logging` 不会把它清掉。
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.addFilter(RequestIdFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def capture_records() -> Iterator[_CaptureHandler]:
    handler = _CaptureHandler()
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def _build_app(image_root: Path, level: str) -> FastAPI:
    settings = Settings(
        image_storage_backend="local",
        image_local_root=image_root,
        log_level=level,
    )
    return create_app(settings, catalog=EmptyCatalogRepository())


def _request_ids(handler: _CaptureHandler) -> list[str | None]:
    return [getattr(record, "request_id", None) for record in handler.records]


def test_log_level_from_settings_is_applied(image_root: Path) -> None:
    _build_app(image_root, "WARNING")

    logger = logging.getLogger(LOGGER_NAME)
    assert logger.level == logging.WARNING
    assert not logger.isEnabledFor(logging.INFO)


def test_debug_level_enables_debug_records(image_root: Path) -> None:
    _build_app(image_root, "DEBUG")

    assert logging.getLogger(LOGGER_NAME).isEnabledFor(logging.DEBUG)


def test_startup_log_is_emitted_without_request_id(image_root: Path) -> None:
    with capture_records() as handler:
        _build_app(image_root, "INFO")

    assert any("服务已装配" in record.getMessage() for record in handler.records)
    # 启动日志没有请求上下文，按格式记 `-`。
    assert set(_request_ids(handler)) == {"-"}


def test_request_entry_and_503_logs_carry_request_id(image_root: Path) -> None:
    app = _build_app(image_root, "INFO")

    with capture_records() as handler, TestClient(app) as client:
        response = client.post(
            "/internal/v1/rag/query",
            json=QUERY_BODY,
            headers={"X-Request-Id": REQUEST_ID},
        )

    assert response.status_code == 503
    assert handler.records, "请求过程没有产生日志"
    assert set(_request_ids(handler)) == {REQUEST_ID}
    assert any(record.levelno == logging.WARNING for record in handler.records)


def test_missing_request_id_header_generates_one_for_logs(image_root: Path) -> None:
    app = _build_app(image_root, "INFO")

    with capture_records() as handler, TestClient(app) as client:
        client.get("/internal/v1/books")

    assert handler.records
    assert all(REQUEST_ID_PATTERN.fullmatch(record_id or "") for record_id in _request_ids(handler))

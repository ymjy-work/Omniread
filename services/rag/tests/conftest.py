"""测试夹具：本地文件系统插图存储 + 端口可注入的应用实例。

检索链显式传 `retrieval=None`：默认的 `create_app` 会按环境变量装配真实检索链，
那取决于跑测试时的机器状态（有没有库凭据 / provider 凭据）。测试需要确定路径，
注入替身由各测试自己做。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from helpers import FakeQueryRunner
from omniread.api.app import create_app
from omniread.application.ports import QueryRunner, RetrievalService
from omniread.config import Settings
from omniread.infrastructure.db.catalog import EmptyCatalogRepository
from omniread.infrastructure.objectstore.local import LocalFileSystemImageStorage


@pytest.fixture
def image_root(tmp_path: Path) -> Path:
    root = tmp_path / "images"
    target = root / "books" / "1" / "images" / "01_第1卷"
    target.mkdir(parents=True)
    (target / "007.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    (root / "secret.txt").write_text("不应被读到", encoding="utf-8")
    return root


def _build_client(image_root: Path, query_runner: QueryRunner | None = None) -> TestClient:
    settings = Settings(image_storage_backend="local", image_local_root=image_root)
    app = create_app(
        settings,
        catalog=EmptyCatalogRepository(),
        image_storage=LocalFileSystemImageStorage(image_root),
        query_runner=query_runner,
        retrieval=None,
    )
    return TestClient(app)


def build_client_with_retrieval(
    image_root: Path, retrieval: RetrievalService
) -> TestClient:
    """给需要真跑检索路径的测试用：注入替身检索服务，其余依赖照默认。"""
    settings = Settings(image_storage_backend="local", image_local_root=image_root)
    app = create_app(
        settings,
        catalog=EmptyCatalogRepository(),
        image_storage=LocalFileSystemImageStorage(image_root),
        retrieval=retrieval,
    )
    return TestClient(app)


def build_client_with_runner(image_root: Path, query_runner: QueryRunner) -> TestClient:
    """给需要真跑问答路径的测试用：注入 runner，检索链显式不接线。"""
    return _build_client(image_root, query_runner)


@pytest.fixture
def client(image_root: Path) -> Iterator[TestClient]:
    """默认应用：rag 端点走 UnimplementedQueryRunner，以 RAG_UNAVAILABLE 收尾。"""
    with _build_client(image_root) as test_client:
        yield test_client


@pytest.fixture
def streaming_client(image_root: Path) -> Iterator[TestClient]:
    """注入假事件流的应用：用于验证适配器在真实 HTTP 路径上的编码结果。"""
    with _build_client(image_root, FakeQueryRunner()) as test_client:
        yield test_client

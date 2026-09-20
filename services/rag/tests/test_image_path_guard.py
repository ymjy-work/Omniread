"""插图路径防护：目录穿越（归一化后判前缀）与扩展名白名单。

路径由客户端传来，不能信，因此两类攻击向量都要有单测，且在存储层再复核一次。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omniread.domain.errors import UnsafeImagePath
from omniread.infrastructure.objectstore.local import LocalFileSystemImageStorage
from omniread.infrastructure.objectstore.paths import image_key_prefix, resolve_image_key


def test_legal_relative_path_becomes_book_scoped_key() -> None:
    assert resolve_image_key(1, "01_第1卷/007.jpg") == "books/1/images/01_第1卷/007.jpg"


@pytest.mark.parametrize(
    "raw",
    [
        "./007.jpg",
        "sub/../007.jpg",
        "01_第1卷//007.jpg",
    ],
)
def test_in_book_normalization_is_allowed(raw: str) -> None:
    assert resolve_image_key(1, raw).startswith(image_key_prefix(1))


@pytest.mark.parametrize(
    "raw",
    [
        "../secret.jpg",
        "../../etc/passwd.jpg",
        "01_第1卷/../../secret.jpg",
        "01_第1卷/../../../1/images/007.jpg",
        "..",
        "01/..",
        "/etc/passwd.jpg",
        "C:/windows/007.jpg",
        "01_第1卷\\..\\..\\secret.jpg",
        "..%2fsecret.jpg",
        "%2e%2e/secret.jpg",
        "01%2F007.jpg",
        "%252e%252e%2fsecret.jpg",
        "",
    ],
)
def test_traversal_and_encoded_evasions_are_rejected(raw: str) -> None:
    with pytest.raises(UnsafeImagePath):
        resolve_image_key(1, raw)


@pytest.mark.parametrize(
    "raw",
    [
        "01_第1卷/007.txt",
        "01_第1卷/007.exe",
        "01_第1卷/007",
        "01_第1卷/007.jpg.exe",
        "01_第1卷/.jpg",
    ],
)
def test_extension_whitelist_rejects_non_image(raw: str) -> None:
    with pytest.raises(UnsafeImagePath):
        resolve_image_key(1, raw)


def test_other_book_prefix_is_not_reachable() -> None:
    with pytest.raises(UnsafeImagePath):
        resolve_image_key(2, "../1/images/007.jpg")
    assert resolve_image_key(2, "007.png") == "books/2/images/007.png"


def test_local_storage_reads_inside_root(image_root: Path) -> None:
    storage = LocalFileSystemImageStorage(image_root)
    stored = storage.get("books/1/images/01_第1卷/007.jpg")

    assert stored is not None
    assert stored.data.startswith(b"\xff\xd8")
    assert stored.content_type == "image/jpeg"


def test_local_storage_refuses_path_outside_root(image_root: Path, tmp_path: Path) -> None:
    (tmp_path / "outside.jpg").write_bytes(b"outside")
    storage = LocalFileSystemImageStorage(image_root)

    assert storage.get("../outside.jpg") is None
    assert storage.get("books/1/images/01_第1卷/nope.jpg") is None


def test_http_serves_whitelisted_image(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/images/01_第1卷/007.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")


def test_http_rejects_encoded_traversal(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/images/%2e%2e%2f%2e%2e%2fsecret.txt")

    assert response.status_code == 400
    assert response.json()["code"] == "RAG_INVALID_REALM"


def test_http_rejects_non_whitelisted_extension(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/images/01_第1卷/007.txt")

    assert response.status_code == 400


def test_http_missing_image_returns_not_found(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/images/01_第1卷/999.jpg")

    assert response.status_code == 404
    assert set(response.json()) == {"request_id", "code", "message"}

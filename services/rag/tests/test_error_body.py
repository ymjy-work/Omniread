"""统一错误体形状：`{request_id, code, message}` 三字段扁平、只覆盖非 2xx。"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from helpers import REQUEST_ID
from omniread.api.deps import sanitize_request_id
from omniread.domain.errors import (
    ErrorCode,
    RagInvalidRealm,
    RagInvalidRequest,
    ResourceNotFound,
    error_from_wire,
)

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")
ALLOWED_CODES = {code.value for code in ErrorCode}


def _assert_error_body(payload: dict[str, str], expected_code: str) -> None:
    assert set(payload) == {"request_id", "code", "message"}
    assert payload["code"] == expected_code
    assert payload["code"] in ALLOWED_CODES
    assert REQUEST_ID_PATTERN.fullmatch(payload["request_id"])
    assert payload["message"]
    assert "\n" not in payload["message"]
    assert "Traceback" not in payload["message"]


def test_invalid_body_returns_flat_error_body(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/rag/query",
        json={"book_id": 1, "question": "q", "level": "past", "progress": 0},
    )

    assert response.status_code == 400
    _assert_error_body(response.json(), "RAG_INVALID_REQUEST")


def test_missing_required_field_returns_flat_error_body(client: TestClient) -> None:
    response = client.post("/internal/v1/rag/query", json={})

    assert response.status_code == 400
    _assert_error_body(response.json(), "RAG_INVALID_REQUEST")


@pytest.mark.parametrize(
    "body",
    [
        {"book_id": 1, "question": "", "level": "past"},
        {"book_id": 1, "question": "q", "level": "future"},
        {"book_id": 1, "question": "q", "level": "past", "progress": 0},
    ],
)
def test_schema_violations_are_invalid_request(client: TestClient, body: dict) -> None:
    """**与 schema 对不上的取值归 REQUEST，不归 REALM**。

    判据不是「这个字段叫什么」而是「这一条是不是 schema 里写明的约束」：`progress` 的
    `ge=1` 是 schema 写的固定下界，越界即请求本身不合法。**上界不写进 schema**——
    「这本书有多少章」只有拿到书目录才知道，那是 REALM，由 Java 在 API 边界判
    （`RealmValidator`）。两者同为 400，前端按 code 分支——混在一起就分不出该提示谁。
    """
    response = client.post("/internal/v1/rag/query", json=body)

    assert response.status_code == 400
    _assert_error_body(response.json(), "RAG_INVALID_REQUEST")


def test_the_two_bad_request_codes_are_two_things() -> None:
    """上半条的另一半：两个 400 必须是两个码、两个类、两条分支。

    这条不走 HTTP：上面的 `client` 是个**未接线**的应用（检索链没有实现），语义层的
    realm 检查根本到不了——它要拿到书目录才判得了。所以这里只钉「码 → 类」的映射，
    而真实触发 REALM 的那几处（`level=past` 却没带 progress、progress 超出本书章节数）
    由检索链自己的用例覆盖。
    """
    assert ErrorCode.RAG_INVALID_REALM != ErrorCode.RAG_INVALID_REQUEST
    assert RagInvalidRealm("x").http_status == 400
    assert RagInvalidRequest("x").http_status == 400
    # 映射表漏一项的后果是 `error_from_wire` 抛 KeyError——而那发生在**构造错误响应时**，
    # 也就是最不该再抛异常的时刻。
    assert isinstance(error_from_wire("RAG_INVALID_REALM", "x"), RagInvalidRealm)
    assert isinstance(error_from_wire("RAG_INVALID_REQUEST", "x"), RagInvalidRequest)
    assert isinstance(error_from_wire("RAG_NOT_FOUND", "x"), ResourceNotFound)


def test_not_found_uses_error_body(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/chapters/17")

    assert response.status_code == 404
    _assert_error_body(response.json(), "RAG_NOT_FOUND")


def test_valid_request_id_header_is_passed_through() -> None:
    assert sanitize_request_id(REQUEST_ID) == REQUEST_ID


@pytest.mark.parametrize("candidate", [None, "", "not-a-request-id", "req_XYZ", "req_" + "a" * 31])
def test_malformed_request_id_is_replaced(candidate: str | None) -> None:
    generated = sanitize_request_id(candidate)

    assert REQUEST_ID_PATTERN.fullmatch(generated)
    assert generated != candidate


def test_error_body_echoes_valid_request_id(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/rag/query",
        json={},
        headers={"X-Request-Id": REQUEST_ID},
    )

    assert response.json()["request_id"] == REQUEST_ID

"""统一错误体形状：`{request_id, code, message}` 三字段扁平、只覆盖非 2xx。"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from helpers import REQUEST_ID
from omniread.api.deps import sanitize_request_id
from omniread.domain.errors import ErrorCode

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
    _assert_error_body(response.json(), "RAG_INVALID_REALM")


def test_missing_required_field_returns_flat_error_body(client: TestClient) -> None:
    response = client.post("/internal/v1/rag/query", json={})

    assert response.status_code == 400
    _assert_error_body(response.json(), "RAG_INVALID_REALM")


@pytest.mark.parametrize(
    "body",
    [
        {"book_id": 1, "question": "", "level": "past"},
        {"book_id": 1, "question": "q", "level": "future"},
        {"book_id": 1, "question": "q", "level": "past", "progress": 0},
        {"book_id": 1, "question": "q", "level": "past", "progress": 194},
    ],
)
def test_query_request_validation_uses_error_body(client: TestClient, body: dict) -> None:
    response = client.post("/internal/v1/rag/query", json=body)

    assert response.status_code == 400
    _assert_error_body(response.json(), "RAG_INVALID_REALM")


def test_not_found_uses_error_body(client: TestClient) -> None:
    response = client.get("/internal/v1/books/1/chapters/17")

    assert response.status_code == 404
    _assert_error_body(response.json(), "RAG_INVALID_REALM")


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

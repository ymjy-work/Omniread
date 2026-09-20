"""向量召回的 SQL 形状与前置校验（M0-01 §4.2）。

不连库：用能捕获 SQL 的会话替身，核对 WHERE 过滤条件与执行前的维度校验。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.dialects import postgresql

from omniread.infrastructure.db.models import EMBEDDING_DIM
from omniread.pipelines.retrieval.dense import PgVectorDenseIndex

QUERY = [0.0] * EMBEDDING_DIM


class _EmptyResult:
    def all(self) -> list[Any]:
        return []


class _CapturingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    def __enter__(self) -> _CapturingSession:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, statement: Any) -> _EmptyResult:
        self.statements.append(statement)
        return _EmptyResult()


def _index_with(sessions: list[_CapturingSession]) -> PgVectorDenseIndex:
    def factory() -> _CapturingSession:
        session = _CapturingSession()
        sessions.append(session)
        return session

    return PgVectorDenseIndex(cast(Any, factory))


def _compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_search_filters_realm_and_unembedded_rows_in_sql() -> None:
    sessions: list[_CapturingSession] = []
    index = _index_with(sessions)

    hits = index.search(QUERY, book_id=1, lo=3, hi=9, k=60)

    assert hits == []
    assert len(sessions) == 1
    sql = _compiled(sessions[0].statements[0])
    # realm 与「可检索行」都必须在 WHERE 里，不能取回候选再在应用层筛。
    assert "chunks.embedding IS NOT NULL" in sql
    assert "chunks.book_id" in sql
    assert "chunks.chapter_index" in sql
    # 余弦距离算子与 HNSW 可用的排序形状。
    assert "<=>" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql


def test_search_rejects_wrong_vector_dimension_before_opening_a_session() -> None:
    sessions: list[_CapturingSession] = []
    index = _index_with(sessions)

    with pytest.raises(ValueError, match="1024"):
        index.search([0.1, 0.2], book_id=1, lo=1, hi=9, k=60)

    assert sessions == []


def test_search_rejects_non_positive_k() -> None:
    sessions: list[_CapturingSession] = []
    index = _index_with(sessions)

    with pytest.raises(ValueError):
        index.search(QUERY, book_id=1, lo=1, hi=9, k=0)

"""查询链编排（M0-01 §4.1）：normalize → realm → dense → BM25 → RRF → rerank → 装配。

全部用内存替身与假 provider，不发真实网络请求、不连库。dense 替身模拟「embedding 全是
NULL 时召回 0 条」的真实现状，验证链路仍由 BM25 走通。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from conftest import build_client_with_retrieval
from omniread.domain.errors import RagInvalidRealm
from omniread.domain.models import QueryRequest, RealmLevel
from omniread.infrastructure.providers.errors import ProviderResponseError
from omniread.infrastructure.providers.fake import FakeEmbeddingModel, FakeRerankModel
from omniread.pipelines.retrieval.dense import DenseHit
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline
from omniread.pipelines.retrieval.types import ChunkRecord

QUERY = "艾莉 俄语"
LONE_QUERY = "独有词"


def _chapter_id(chapter: int) -> str:
    return f"book:1:chapter:{chapter}"


def _key(chapter: int, index: int) -> str:
    return f"{_chapter_id(chapter)}#c{index}"


def _build_book(chapters: int, per_chapter: int, *, tokens: int = 100) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    for chapter in range(1, chapters + 1):
        for index in range(per_chapter):
            records.append(
                ChunkRecord(
                    chunk_key=_key(chapter, index),
                    chapter_index=chapter,
                    chunk_index=index,
                    content=f"第{chapter}章 第{index}段 艾莉 俄语",
                    token_count=tokens,
                    prev_chunk_key=_key(chapter, index - 1) if index > 0 else None,
                    next_chunk_key=(
                        _key(chapter, index + 1) if index + 1 < per_chapter else None
                    ),
                )
            )
    return records


class InMemoryChunkStore:
    """只读 chunk 视图；按 `(chapter_index, chunk_index)` 升序返回。"""

    def __init__(self, records: Sequence[ChunkRecord], *, empty: bool = False) -> None:
        self._records = [] if empty else list(records)

    def book_chapter_range(self, book_id: int) -> tuple[int, int] | None:
        if not self._records:
            return None
        chapters = [record.chapter_index for record in self._records]
        return min(chapters), max(chapters)

    def load_chunks(self, book_id: int) -> Sequence[ChunkRecord]:
        return list(self._records)


class RecordingDenseIndex:
    """记录 SQL WHERE 收到的 realm 区间，并按区间过滤内存里的命中。

    `rows` 为空表示库中 `embedding IS NOT NULL` 的行数为 0，dense 一路必须如实返回 0 条，
    不能假定全都有向量。
    """

    def __init__(self, chapter_of: dict[str, int], *, rows: Sequence[str] = ()) -> None:
        self._chapter_of = chapter_of
        self._rows = list(rows)
        self.calls: list[tuple[int, int, int]] = []

    def search(
        self, query_vector: Sequence[float], *, book_id: int, lo: int, hi: int, k: int
    ) -> Sequence[DenseHit]:
        self.calls.append((lo, hi, k))
        in_realm = [
            key for key in self._rows if lo <= self._chapter_of[key] <= hi
        ]
        return [
            DenseHit(chunk_key=key, score=1.0 - rank / 100.0)
            for rank, key in enumerate(in_realm[:k])
        ]


def _pipeline(
    records: Sequence[ChunkRecord],
    *,
    rows: Sequence[str] | None = None,
    embedder: FakeEmbeddingModel | None = None,
) -> tuple[RetrievalPipeline, RecordingDenseIndex]:
    chapter_of = {record.chunk_key: record.chapter_index for record in records}
    dense = RecordingDenseIndex(
        chapter_of,
        rows=list(rows) if rows is not None else [record.chunk_key for record in records],
    )
    pipeline = RetrievalPipeline(
        store=InMemoryChunkStore(records),
        dense=dense,
        embedder=embedder or FakeEmbeddingModel(),
        reranker=FakeRerankModel(),
    )
    return pipeline, dense


def _request(
    question: str = QUERY,
    *,
    level: RealmLevel = RealmLevel.FULL,
    progress: int | None = None,
) -> QueryRequest:
    return QueryRequest(book_id=1, question=question, level=level, progress=progress)


async def test_pipeline_runs_every_stage_and_closes_with_assembly() -> None:
    records = _build_book(6, 3)
    pipeline, dense = _pipeline(records)

    outcome = await pipeline.retrieve(_request())

    assert outcome.query == QUERY
    assert outcome.realm.lo == 1 and outcome.realm.hi == 6
    assert dense.calls == [(1, 6, 60)]
    assert outcome.kw and outcome.dense and outcome.fused and outcome.reranked
    assert len(outcome.reranked) <= 24
    assert len(outcome.assembled) <= 8
    assert all(item.chapter_index in range(1, 7) for item in outcome.assembled)


async def test_dense_with_no_embedded_rows_recalls_nothing_but_keyword_path_works() -> None:
    # embedding 全为 NULL：dense 0 条，BM25 仍要能跑通整条链。
    records = _build_book(3, 2)
    pipeline, _ = _pipeline(records, rows=[])

    outcome = await pipeline.retrieve(_request())

    assert outcome.dense == ()
    assert outcome.kw
    assert outcome.reranked
    assert outcome.assembled


async def test_past_realm_filters_both_routes_and_assembly() -> None:
    records = _build_book(6, 3)
    pipeline, dense = _pipeline(records)

    outcome = await pipeline.retrieve(_request(level=RealmLevel.PAST, progress=3))

    assert (outcome.realm.lo, outcome.realm.hi) == (1, 3)
    assert dense.calls == [(1, 3, 60)]
    for stage in (outcome.dense, outcome.kw, outcome.fused, outcome.reranked, outcome.assembled):
        assert stage
        assert all(item.chapter_index <= 3 for item in stage)


async def test_full_realm_spans_the_whole_book() -> None:
    records = _build_book(4, 2)
    pipeline, dense = _pipeline(records)

    outcome = await pipeline.retrieve(_request(level=RealmLevel.FULL))

    assert (outcome.realm.lo, outcome.realm.hi) == (1, 4)
    assert dense.calls == [(1, 4, 60)]


async def test_query_normalization_is_applied_before_retrieval() -> None:
    records = _build_book(3, 2)
    pipeline, _ = _pipeline(records)

    padded = await pipeline.retrieve(_request("  艾莉　俄语  "))

    assert padded.query == QUERY
    assert [hit.chunk_key for hit in padded.kw] == [
        hit.chunk_key for hit in (await pipeline.retrieve(_request())).kw
    ]


async def test_empty_query_is_rejected() -> None:
    records = _build_book(2, 2)
    pipeline, _ = _pipeline(records)

    with pytest.raises(RagInvalidRealm):
        await pipeline.retrieve(_request("   　  "))


async def test_rerank_pool_is_capped_at_rerank_k() -> None:
    records = _build_book(30, 1)
    pipeline, _ = _pipeline(records)

    outcome = await pipeline.retrieve(_request())

    assert len(outcome.fused) > 24
    assert len(outcome.reranked) == 24


async def test_embedding_dimension_mismatch_fails_fast() -> None:
    records = _build_book(2, 2)
    with pytest.raises(ValueError, match="1024"):
        _pipeline(records, embedder=FakeEmbeddingModel(dim=8))


async def test_query_vector_of_wrong_length_is_a_provider_response_error() -> None:
    records = _build_book(2, 2)

    class ShortVectorEmbedder(FakeEmbeddingModel):
        async def embed_query(self, text: str) -> list[float]:
            return [0.0] * 8

    pipeline, _ = _pipeline(records, embedder=ShortVectorEmbedder())

    with pytest.raises(ProviderResponseError):
        await pipeline.retrieve(_request())


async def test_neighbor_expand_false_keeps_hits_only() -> None:
    records = _build_book(1, 3)
    only = [_key(1, 1)]
    lone_records = [
        ChunkRecord(
            chunk_key=record.chunk_key,
            chapter_index=record.chapter_index,
            chunk_index=record.chunk_index,
            content=(f"独有词 {record.chunk_key}" if record.chunk_key in only else "无关内容"),
            token_count=record.token_count,
            prev_chunk_key=record.prev_chunk_key,
            next_chunk_key=record.next_chunk_key,
        )
        for record in records
    ]
    chapter_of = {record.chunk_key: record.chapter_index for record in lone_records}
    dense = RecordingDenseIndex(chapter_of, rows=only)
    pipeline = RetrievalPipeline(
        store=InMemoryChunkStore(lone_records),
        dense=dense,
        embedder=FakeEmbeddingModel(),
        reranker=FakeRerankModel(),
    )

    expanded = await pipeline.retrieve(_request(question=LONE_QUERY))
    plain = await pipeline.retrieve(
        QueryRequest(
            book_id=1,
            question=LONE_QUERY,
            level=RealmLevel.FULL,
            neighbor_expand=False,
        )
    )

    assert any(item.source == "neighbor" for item in expanded.assembled)
    assert [item.source for item in plain.assembled] == ["hit"]


def test_retrieval_only_returns_untruncated_stage_lists(image_root) -> None:
    # 30 章各 1 段：kw / fused 都会超过 10 条，响应必须一条不截；assembled 只报最终集合。
    records = _build_book(30, 1)
    pipeline, _ = _pipeline(records)
    client: TestClient = build_client_with_retrieval(image_root, pipeline)

    response = client.post(
        "/internal/v1/rag/retrieval-only",
        json={"book_id": 1, "question": QUERY, "level": "full"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"request_id", "realm", "stages", "dropped"}
    assert body["realm"] == {"lo": 1, "hi": 30}
    assert set(body["stages"]) == {"dense", "kw", "fused", "rerank", "assembled"}
    assert len(body["stages"]["kw"]) == 30
    assert len(body["stages"]["fused"]) == 30
    assert len(body["stages"]["rerank"]) == 24
    assert len(body["stages"]["assembled"]) <= 8
    for hit in body["stages"]["kw"]:
        assert set(hit) == {"chunk_key", "chapter_index", "score", "rank"}
    for item in body["stages"]["assembled"]:
        assert set(item) == {"chunk_key", "chapter_index", "source"}


def test_retrieval_only_past_mode_reports_realm_and_no_leak(image_root) -> None:
    records = _build_book(6, 2)
    pipeline, _ = _pipeline(records)
    client: TestClient = build_client_with_retrieval(image_root, pipeline)

    response = client.post(
        "/internal/v1/rag/retrieval-only",
        json={"book_id": 1, "question": QUERY, "level": "past", "progress": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["realm"] == {"lo": 1, "hi": 2}
    for stage in body["stages"].values():
        assert all(item["chapter_index"] <= 2 for item in stage)

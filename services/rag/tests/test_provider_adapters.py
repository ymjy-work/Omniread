"""Provider 单测：假 provider 的确定性、百炼适配器的协议解析与错误映射。

全程走 `httpx.MockTransport`，一次真实 API 调用都不发；凭据用测试串，不读环境变量。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from omniread.domain.errors import RagProviderError, RagTimeout
from omniread.infrastructure.db.models import EMBEDDING_DIM as DB_EMBEDDING_DIM
from omniread.infrastructure.providers import (
    RERANK_MODEL,
    AliEmbeddingAdapter,
    AliRerankAdapter,
    EmbeddingModel,
    FakeEmbeddingModel,
    FakeRerankModel,
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
    RerankModel,
    to_rag_error,
)
from omniread.infrastructure.providers.ali import DASHSCOPE_API_KEY_ENV, EMBEDDING_DIM

TEST_KEY = "test-key-not-a-real-credential"


def _accepts_embedding_model(model: EmbeddingModel) -> None:
    """形参声明即校验：假 provider 与百炼适配器都必须满足接口。"""


def _accepts_rerank_model(model: RerankModel) -> None:
    """同上，rerank 侧。"""


def test_adapters_satisfy_provider_interfaces() -> None:
    _accepts_embedding_model(FakeEmbeddingModel())
    _accepts_embedding_model(AliEmbeddingAdapter(api_key=TEST_KEY))
    _accepts_rerank_model(FakeRerankModel())
    _accepts_rerank_model(AliRerankAdapter(api_key=TEST_KEY))


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fake_embedding_is_deterministic() -> None:
    first = await FakeEmbeddingModel(dim=8).embed_documents(["阿尔法", "贝塔"])
    second = await FakeEmbeddingModel(dim=8).embed_documents(["阿尔法", "贝塔"])

    assert first == second
    assert len(first) == 2
    assert all(len(vector) == 8 for vector in first)
    assert first[0] != first[1]


async def test_fake_embedding_query_matches_document_vector() -> None:
    texts = ["阿尔法在图书馆阅读。"]
    documents = await FakeEmbeddingModel(dim=16).embed_documents(texts)
    query = await FakeEmbeddingModel(dim=16).embed_query(texts[0])

    assert query == documents[0]


def test_fake_and_ali_embedding_dim_follow_the_column() -> None:
    assert EMBEDDING_DIM == DB_EMBEDDING_DIM
    assert FakeEmbeddingModel().dim == DB_EMBEDDING_DIM


async def test_fake_rerank_is_deterministic() -> None:
    documents = ["甲", "乙", "丙"]
    first = await FakeRerankModel().rerank("查询", documents)
    second = await FakeRerankModel().rerank("查询", documents)

    assert first == second
    assert sorted(result.index for result in first) == [0, 1, 2]
    scores = [result.score for result in first]
    assert scores == sorted(scores, reverse=True)


async def test_fake_rerank_honours_top_n() -> None:
    documents = ["甲", "乙", "丙"]
    full = await FakeRerankModel().rerank("查询", documents)

    assert await FakeRerankModel().rerank("查询", documents, top_n=2) == full[:2]


def test_ali_adapters_fail_fast_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DASHSCOPE_API_KEY_ENV, raising=False)

    with pytest.raises(ProviderConfigError):
        AliEmbeddingAdapter()
    with pytest.raises(ProviderConfigError):
        AliRerankAdapter()


async def test_ali_embedding_batches_and_restores_order() -> None:
    dim = 4
    payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        count = len(payload["input"])
        # 故意乱序返回：适配器必须按 data[].index 回填，而不是按数组位置。
        data = [
            {"index": index, "embedding": [float(index)] * dim} for index in reversed(range(count))
        ]
        return httpx.Response(200, json={"data": data})

    async with _client(handler) as client:
        adapter = AliEmbeddingAdapter(api_key=TEST_KEY, dim=dim, batch_size=10, client=client)
        vectors = await adapter.embed_documents([f"文本{index}" for index in range(25)])

    assert len(vectors) == 25
    assert [len(payload["input"]) for payload in payloads] == [10, 10, 5]
    assert all(payload["dimensions"] == dim for payload in payloads)
    assert vectors[0][0] == pytest.approx(0.0)
    assert vectors[1][0] == pytest.approx(1.0)
    assert vectors[10][0] == pytest.approx(0.0)


async def test_ali_embedding_query_uses_single_text_batch() -> None:
    payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

    async with _client(handler) as client:
        adapter = AliEmbeddingAdapter(api_key=TEST_KEY, dim=2, client=client)
        vector = await adapter.embed_query("查询")

    assert vector == [0.5, 0.5]
    assert payloads[0]["input"] == ["查询"]


async def test_ali_rerank_parses_sorts_and_forwards_top_n() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": {
                    "results": [
                        {"index": 2, "relevance_score": 0.2},
                        {"index": 0, "relevance_score": 0.9},
                    ]
                }
            },
        )

    async with _client(handler) as client:
        adapter = AliRerankAdapter(api_key=TEST_KEY, client=client)
        results = await adapter.rerank("查询", ["甲", "乙", "丙"], top_n=2)

    assert [result.index for result in results] == [0, 2]
    assert results[0].score == pytest.approx(0.9)
    assert captured["model"] == RERANK_MODEL
    assert captured["input"] == {"query": "查询", "documents": ["甲", "乙", "丙"]}
    assert captured["parameters"] == {"return_documents": False, "top_n": 2}


async def test_ali_rerank_empty_documents_skips_the_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("空文档不该发请求")

    async with _client(handler) as client:
        adapter = AliRerankAdapter(api_key=TEST_KEY, client=client)
        assert await adapter.rerank("查询", []) == []


async def test_ali_http_error_maps_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "InternalError"})

    async with _client(handler) as client:
        adapter = AliEmbeddingAdapter(api_key=TEST_KEY, dim=2, client=client)
        with pytest.raises(ProviderError) as info:
            await adapter.embed_query("查询")

    error = info.value
    assert error.status_code == 500
    assert TEST_KEY not in str(error)
    rag_error = to_rag_error(error)
    assert isinstance(rag_error, RagProviderError)
    assert rag_error.http_status == 502


async def test_ali_timeout_maps_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    async with _client(handler) as client:
        adapter = AliEmbeddingAdapter(api_key=TEST_KEY, dim=2, client=client)
        with pytest.raises(ProviderTimeoutError) as info:
            await adapter.embed_query("查询")

    rag_error = to_rag_error(info.value)
    assert isinstance(rag_error, RagTimeout)
    assert rag_error.http_status == 504


async def test_ali_embedding_dimension_mismatch_is_a_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

    async with _client(handler) as client:
        adapter = AliEmbeddingAdapter(api_key=TEST_KEY, dim=2, client=client)
        with pytest.raises(ProviderResponseError):
            await adapter.embed_query("查询")


async def test_ali_rerank_rejects_out_of_range_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"output": {"results": [{"index": 9, "relevance_score": 1}]}}
        )

    async with _client(handler) as client:
        adapter = AliRerankAdapter(api_key=TEST_KEY, client=client)
        with pytest.raises(ProviderResponseError):
            await adapter.rerank("查询", ["甲"])

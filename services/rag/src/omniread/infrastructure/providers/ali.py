"""阿里云百炼适配器：embedding 与 rerank（M0-01 §5.2）。

两个端点协议不同，各按各的写：

- embedding 走 OpenAI 兼容面 `POST {base_url}/embeddings`（`data[].embedding` 按
  `index` 回填）；批量上限按百炼的 10 条切批，`embed_documents` 对内自动分批。
- rerank 走 DashScope 原生面 `POST .../text-rerank/text-rerank`
  （`input.query` + `input.documents` → `output.results[].relevance_score`）。

凭据只读环境变量 `DASHSCOPE_API_KEY`，缺失时构造即抛 `ProviderConfigError`：不做静默
降级，也不在日志里回显密钥。所有网络与响应错误统一成 `ProviderError` 子类。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import httpx

from omniread.infrastructure.providers.base import RerankResult
from omniread.infrastructure.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
)

DASHSCOPE_API_KEY_ENV = "DASHSCOPE_API_KEY"

# 与 `chunks.embedding` 的列维度绑定（M0-02 §3.4）；不一致的向量入库即污染索引。
EMBEDDING_DIM = 1024

EMBEDDING_MODEL = "qwen3.7-text-embedding"
RERANK_MODEL = "qwen3.7-text-rerank"

DASHSCOPE_COMPAT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_RERANK_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)

# 百炼兼容面单次 embedding 请求的文本条数上限。
EMBEDDING_BATCH_SIZE = 10

DEFAULT_TIMEOUT_SECONDS = 30.0

_PROVIDER_NAME = "dashscope"


def _resolve_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get(DASHSCOPE_API_KEY_ENV)
    if not key:
        raise ProviderConfigError(
            f"{DASHSCOPE_API_KEY_ENV} 未注入：百炼凭据只从环境变量读，不设默认值",
            provider=_PROVIDER_NAME,
        )
    return key


class _AliHttpClient:
    """两个百炼适配器共用的 HTTP 层：鉴权头、超时映射、JSON 解析。"""

    def __init__(
        self,
        *,
        api_key: str | None,
        timeout: float,
        client: httpx.AsyncClient | None,
    ) -> None:
        self._api_key = _resolve_api_key(api_key)
        self._timeout = timeout
        # 注入的 client 生命周期归调用方（测试用 MockTransport 走这条）；
        # 未注入时懒建一个，连接复用，由 aclose() 释放。
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """释放自建连接池；注入的 client 不动。"""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = await self._http().post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                "百炼请求超时", provider=_PROVIDER_NAME
            ) from exc
        except httpx.HTTPError as exc:
            # 连接失败 / DNS 失败等：不带上原始异常文本里的 URL 与主机细节。
            raise ProviderError("百炼请求失败", provider=_PROVIDER_NAME) from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"百炼返回 HTTP {response.status_code}",
                provider=_PROVIDER_NAME,
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseError("百炼响应不是 JSON", provider=_PROVIDER_NAME) from exc
        if not isinstance(body, dict):
            raise ProviderResponseError("百炼响应不是 JSON 对象", provider=_PROVIDER_NAME)
        return body


class AliEmbeddingAdapter:
    """`EmbeddingModel` 的百炼实现，`dim` 固定 1024。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DASHSCOPE_COMPAT_BASE_URL,
        model: str = EMBEDDING_MODEL,
        dim: int = EMBEDDING_DIM,
        batch_size: int = EMBEDDING_BATCH_SIZE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size 必须为正整数")
        self.model = model
        self.dim = dim
        self._base_url = base_url.rstrip("/")
        self._batch_size = batch_size
        self._http = _AliHttpClient(api_key=api_key, timeout=timeout, client=client)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """按批取向量，返回顺序与入参一致。

        单批内 provider 可能乱序返回，按 `data[].index` 回填而不是按数组位置取。
        """
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(await self._embed_batch(list(texts[start : start + self._batch_size])))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed_batch([text])
        return vectors[0]

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body = await self._http.post_json(
            f"{self._base_url}/embeddings",
            {
                "model": self.model,
                "input": batch,
                "dimensions": self.dim,
                "encoding_format": "float",
            },
        )
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            raise ProviderResponseError(
                "百炼 embedding 响应条数与入参不一致", provider=_PROVIDER_NAME
            )
        ordered: list[list[float] | None] = [None] * len(batch)
        for item in data:
            if not isinstance(item, dict):
                raise ProviderResponseError("百炼 embedding 条目不是对象", provider=_PROVIDER_NAME)
            index = item.get("index")
            embedding = item.get("embedding")
            if not isinstance(index, int) or not 0 <= index < len(batch):
                raise ProviderResponseError(
                    "百炼 embedding 条目的 index 越界", provider=_PROVIDER_NAME
                )
            if not isinstance(embedding, list) or len(embedding) != self.dim:
                raise ProviderResponseError(
                    f"百炼 embedding 维度不是 {self.dim}", provider=_PROVIDER_NAME
                )
            try:
                ordered[index] = [float(value) for value in embedding]
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError(
                    "百炼 embedding 分量不是数值", provider=_PROVIDER_NAME
                ) from exc
        if any(vector is None for vector in ordered):
            raise ProviderResponseError("百炼 embedding 响应缺条目", provider=_PROVIDER_NAME)
        return [vector for vector in ordered if vector is not None]


class AliRerankAdapter:
    """`RerankModel` 的百炼实现。

    输入 24 / 输出 24 是管线口径（M0-00 §5），适配器只转发 `top_n`：不替调用方
    做候选截断之外的任何决策。
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        url: str = DASHSCOPE_RERANK_URL,
        model: str = RERANK_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._url = url
        self._http = _AliHttpClient(api_key=api_key, timeout=timeout, client=client)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int | None = None
    ) -> list[RerankResult]:
        if not documents:
            return []
        if top_n is not None and top_n <= 0:
            raise ValueError("top_n 必须为正整数")
        parameters: dict[str, Any] = {"return_documents": False}
        if top_n is not None:
            parameters["top_n"] = min(top_n, len(documents))
        body = await self._http.post_json(
            self._url,
            {
                "model": self.model,
                "input": {"query": query, "documents": list(documents)},
                "parameters": parameters,
            },
        )
        output = body.get("output")
        results = output.get("results") if isinstance(output, dict) else None
        if not isinstance(results, list):
            raise ProviderResponseError("百炼 rerank 响应缺 results", provider=_PROVIDER_NAME)
        ranked: list[RerankResult] = []
        for item in results:
            if not isinstance(item, dict):
                raise ProviderResponseError("百炼 rerank 条目不是对象", provider=_PROVIDER_NAME)
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or not 0 <= index < len(documents):
                raise ProviderResponseError(
                    "百炼 rerank 条目的 index 越界", provider=_PROVIDER_NAME
                )
            if not isinstance(score, int | float):
                raise ProviderResponseError(
                    "百炼 rerank 缺 relevance_score", provider=_PROVIDER_NAME
                )
            ranked.append(RerankResult(index=index, score=float(score)))
        ranked.sort(key=lambda result: (-result.score, result.index))
        return ranked

import logging
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.config.settings import settings
from app.db.models import Chunk
from app.vectorstore.vector_db import VectorStore

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[int] | None: ...


def dashscope_rerank_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return (
        f"{parsed.scheme}://{parsed.netloc}"
        "/api/v1/services/rerank/text-rerank/text-rerank"
    )


class DashScopeReranker:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.bailian_api_key
        self._url = dashscope_rerank_url(base_url or settings.bailian_base_url)
        self._model = model or settings.rerank_model
        self._timeout = timeout

    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[int] | None:
        if not documents:
            return []
        if not self._api_key:
            logger.warning("BAILIAN_API_KEY is not configured; using vector order")
            return None

        payload = {
            "model": self._model,
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": False, "top_n": top_n},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                results = response.json()["output"]["results"]
            ordered = sorted(
                results,
                key=lambda item: float(item.get("relevance_score", 0.0)),
                reverse=True,
            )
            indices = [int(item["index"]) for item in ordered]
            return [index for index in indices if 0 <= index < len(documents)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("DashScope rerank failed; using vector order: %s", exc)
            return None


class Retriever:
    def __init__(
        self,
        vector_store: VectorStore,
        reranker: Reranker | None = None,
        *,
        candidate_top_k: int = 30,
    ) -> None:
        self._vector_store = vector_store
        self._reranker = reranker
        self._candidate_top_k = candidate_top_k

    async def retrieve(
        self,
        query: str,
        query_vector: object,
        *,
        book_id: int,
        chapter_start: int,
        chapter_end: int | None,
        top_k: int,
    ) -> list[Chunk]:
        hits = self._vector_store.search(
            book_id,
            chapter_start,
            chapter_end,
            query_vector,
            self._candidate_top_k,
        )
        candidates = [hit.chunk for hit in hits]
        if not candidates:
            return []

        if self._reranker is not None:
            indices = await self._reranker.rerank(
                query, [chunk.text for chunk in candidates], top_k
            )
            if indices:
                ordered: list[Chunk] = []
                seen: set[int] = set()
                for index in indices:
                    if index in seen or not 0 <= index < len(candidates):
                        continue
                    seen.add(index)
                    ordered.append(candidates[index])
                    if len(ordered) == top_k:
                        break
                if ordered:
                    return ordered

        return candidates[:top_k]

import logging
import time
from typing import Any

import numpy as np

from app.config.settings import settings
from app.utils.helpers import l2_normalize, l2_normalize_rows

logger = logging.getLogger(__name__)


class EmbeddingConfigurationError(RuntimeError):
    pass


class Embedder:
    def __init__(
        self,
        client: Any | None = None,
        *,
        batch_size: int = 64,
        max_attempts: int = 3,
        retry_base_seconds: float = 1.0,
    ) -> None:
        self._client = client
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds

    def _get_client(self) -> Any:
        if self._client is None:
            if not settings.bailian_api_key:
                raise EmbeddingConfigurationError("BAILIAN_API_KEY is not configured")
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                base_url=settings.bailian_base_url,
                api_key=settings.bailian_api_key,
                model=settings.embedding_model,
                dimensions=settings.embedding_dim,
                chunk_size=self._batch_size,
                max_retries=0,
            )
        return self._client

    def _with_retry(self, operation: Any, *args: Any) -> Any:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return operation(*args)
            except Exception:
                if attempt == self._max_attempts:
                    raise
                delay = self._retry_base_seconds * (2 ** (attempt - 1))
                logger.warning("embedding request failed; retrying in %.1fs", delay)
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, settings.embedding_dim), dtype=np.float32)

        client = self._get_client()
        batches: list[np.ndarray] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors = self._with_retry(client.embed_documents, batch)
            array = np.asarray(vectors, dtype=np.float32)
            if array.ndim != 2 or array.shape != (len(batch), settings.embedding_dim):
                raise ValueError(
                    "embedding response shape mismatch: "
                    f"expected {(len(batch), settings.embedding_dim)}, got {array.shape}"
                )
            batches.append(l2_normalize_rows(array))

        return np.vstack(batches).astype(np.float32, copy=False)

    def embed_query(self, text: str) -> np.ndarray:
        client = self._get_client()
        vector = np.asarray(
            self._with_retry(client.embed_query, text), dtype=np.float32
        )
        if vector.shape != (settings.embedding_dim,):
            raise ValueError(
                "query embedding shape mismatch: "
                f"expected {(settings.embedding_dim,)}, got {vector.shape}"
            )
        return l2_normalize(vector)

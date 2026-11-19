import asyncio
import logging
from typing import Any

import numpy as np

from app.config.settings import settings
from app.db.models import Chunk
from app.embeddings.embedder import Embedder
from app.ingestion.chunker import DEFAULT_CHUNK_SIZE, chunk_chapters
from app.rag.channels import Channel, load_channels
from app.rag.citations import CitationResult, refusal, validate_citations
from app.rag.generator import Generation, Generator
from app.rag.providers import ChatTarget, redact_secrets
from app.rag.query_rewriter import QueryRewriter
from app.rag.realm import chapter_range
from app.rag.retriever import DashScopeReranker, Reranker, Retriever
from app.schemas import (
    AskRequest,
    AskResponse,
    AskUsage,
    IndexRequest,
    IndexResponse,
)
from app.vectorstore.vector_db import VectorStore

logger = logging.getLogger(__name__)


class ModelGenerationError(RuntimeError):
    pass


class RagPipeline:
    def __init__(
        self,
        *,
        db_path: str | None = None,
        embedder: Any | None = None,
        generator: Any | None = None,
        reranker: Reranker | None = None,
        rewriter: Any | None = None,
        vector_store: VectorStore | None = None,
        channels: list[Channel] | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._embedder = embedder or Embedder()
        self._generator = generator or Generator()
        self._rewriter = rewriter or QueryRewriter()
        self._channels = channels
        self._chunk_size = chunk_size
        self._vector_store = vector_store or VectorStore(
            db_path or settings.rag_db, settings.embedding_dim
        )
        self._retriever = Retriever(
            self._vector_store,
            reranker if reranker is not None else DashScopeReranker(),
        )

    async def index(self, request: IndexRequest) -> IndexResponse:
        drafts = chunk_chapters(request.chapters, chunk_size=self._chunk_size)
        texts = [draft.text for draft in drafts]
        vectors = await asyncio.to_thread(self._embedder.embed_documents, texts)
        matrix = np.asarray(vectors, dtype=np.float32)

        records = [
            (
                draft.chapter_id,
                draft.chapter_index,
                draft.title,
                draft.text,
            )
            for draft in drafts
        ]
        indexed = await asyncio.to_thread(
            self._vector_store.replace_book,
            request.book_id,
            records,
            matrix,
        )
        return IndexResponse(indexed_chunks=indexed)

    async def ask(self, request: AskRequest) -> AskResponse:
        targets = self._resolve_targets(request)
        chapter_start, chapter_end = chapter_range(
            request.level, request.progress
        )
        query = await self._rewriter.rewrite(request.question, request.history)
        query_vector = await asyncio.to_thread(self._embedder.embed_query, query)
        top_k = min(max(request.top_k or 8, 1), 8)
        chunks: list[Chunk] = await self._retriever.retrieve(
            query,
            query_vector,
            book_id=request.book_id,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            top_k=top_k,
        )
        if not chunks:
            return self._to_response(
                refusal(), request.mode, targets[0], prompt_tokens=0,
                completion_tokens=0,
            )

        generation, target = await self._generate(
            request, targets, query, chunks
        )
        result = validate_citations(
            generation.answer, chunks, cited_ids=generation.cited_ids
        )
        return self._to_response(
            result,
            request.mode,
            target,
            prompt_tokens=generation.prompt_tokens,
            completion_tokens=generation.completion_tokens,
        )

    def _resolve_targets(self, request: AskRequest) -> list[ChatTarget]:
        if request.mode == "platform":
            return [
                ChatTarget(
                    provider="bailian",
                    model=request.model or settings.chat_model,
                    api_key=settings.bailian_api_key,
                )
            ]
        if request.mode == "byok":
            return [
                ChatTarget(
                    provider=request.provider or "",
                    model=request.model or "",
                    api_key=request.api_key or "",
                )
            ]

        channels = (
            self._channels if self._channels is not None else load_channels()
        )
        targets = [channel.to_target() for channel in channels]
        if settings.bailian_api_key:
            targets.append(
                ChatTarget(
                    provider="bailian",
                    model=settings.chat_model,
                    api_key=settings.bailian_api_key,
                    fallback=True,
                )
            )
        if not targets:
            targets.append(
                ChatTarget(
                    provider="bailian",
                    model=settings.chat_model,
                    api_key=settings.bailian_api_key,
                    fallback=True,
                )
            )
        return targets

    async def _generate(
        self,
        request: AskRequest,
        targets: list[ChatTarget],
        query: str,
        chunks: list[Chunk],
    ) -> tuple[Generation, ChatTarget]:
        secrets = [target.api_key for target in targets]

        if request.mode != "auto":
            target = targets[0]
            try:
                generation = await self._generator.generate(query, chunks, target)
            except Exception as exc:  # noqa: BLE001
                self._log_generation_failure("generation failed", target, exc, secrets)
                raise ModelGenerationError(
                    f"generation failed: {target}"
                ) from None
            return generation, target

        attempted_channel = False
        fallback_logged = False
        for target in targets:
            if target.fallback and attempted_channel and not fallback_logged:
                logger.warning(
                    "all auto channels failed; falling back to platform "
                    "bailian key"
                )
                fallback_logged = True
            try:
                generation = await self._generator.generate(query, chunks, target)
                return generation, target
            except Exception as exc:  # noqa: BLE001
                self._log_generation_failure(
                    "auto target failed", target, exc, secrets
                )
                if not target.fallback:
                    attempted_channel = True

        raise ModelGenerationError("all auto generation attempts failed") from None

    @staticmethod
    def _log_generation_failure(
        prefix: str,
        target: ChatTarget,
        exc: Exception,
        secrets: list[str],
    ) -> None:
        logger.warning(
            "%s provider=%s model=%s: %s",
            prefix,
            target.provider,
            target.model,
            redact_secrets(str(exc), *secrets),
        )

    @staticmethod
    def _to_response(
        result: CitationResult,
        mode: str,
        target: ChatTarget,
        *,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> AskResponse:
        return AskResponse(
            answer=result.answer,
            citations=result.citations,
            usage=AskUsage(
                mode=mode,
                provider=target.provider,
                model=target.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )
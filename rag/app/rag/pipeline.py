import asyncio
from typing import Any

import numpy as np

from app.config.settings import settings
from app.db.models import Chunk
from app.embeddings.embedder import Embedder
from app.ingestion.chunker import DEFAULT_CHUNK_SIZE, chunk_chapters
from app.rag.citations import CitationResult, refusal, validate_citations
from app.rag.generator import Generator
from app.rag.query_rewriter import QueryRewriter
from app.rag.realm import chapter_range
from app.rag.retriever import DashScopeReranker, Reranker, Retriever
from app.schemas import AskRequest, AskResponse, IndexRequest, IndexResponse
from app.vectorstore.vector_db import VectorStore


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
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._embedder = embedder or Embedder()
        self._generator = generator or Generator()
        self._rewriter = rewriter or QueryRewriter()
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
            return self._to_response(refusal())

        generation = await self._generator.generate(query, chunks)
        result = validate_citations(
            generation.answer, chunks, cited_ids=generation.cited_ids
        )
        return self._to_response(result)

    @staticmethod
    def _to_response(result: CitationResult) -> AskResponse:
        return AskResponse(answer=result.answer, citations=result.citations)

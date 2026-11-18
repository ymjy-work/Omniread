import threading
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.db.models import Chunk
from app.db.sqlite import initialize, session
from app.utils.helpers import blob_to_vector, l2_normalize, vector_to_blob


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class VectorStore:
    def __init__(self, db_path: str, dimension: int) -> None:
        self.db_path = db_path
        self.dimension = dimension
        self._lock = threading.RLock()
        self._chunks: list[Chunk] = []
        self._vectors = np.empty((0, dimension), dtype=np.float32)
        initialize(db_path)
        self.rebuild_cache()

    def rebuild_cache(self) -> None:
        with self._lock:
            with session(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT id, book_id, chapter_id, chapter_index, title, text, vector "
                    "FROM chunk ORDER BY id"
                ).fetchall()

            chunks: list[Chunk] = []
            vectors: list[np.ndarray] = []
            for row in rows:
                vector = blob_to_vector(row["vector"])
                if vector.shape != (self.dimension,):
                    raise ValueError(
                        f"chunk {row['id']} has vector dimension {vector.shape}, "
                        f"expected {(self.dimension,)}"
                    )
                chunks.append(
                    Chunk(
                        id=int(row["id"]),
                        book_id=int(row["book_id"]),
                        chapter_id=str(row["chapter_id"]),
                        chapter_index=int(row["chapter_index"]),
                        title=str(row["title"]),
                        text=str(row["text"]),
                        vector=vector,
                    )
                )
                vectors.append(vector)

            self._chunks = chunks
            if vectors:
                self._vectors = np.vstack(vectors).astype(np.float32, copy=False)
            else:
                self._vectors = np.empty((0, self.dimension), dtype=np.float32)

    def replace_book(
        self,
        book_id: int,
        chunks: list[tuple[str, int, str, str]],
        vectors: np.ndarray,
    ) -> int:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape != (len(chunks), self.dimension):
            raise ValueError(
                "vector matrix shape mismatch: "
                f"expected {(len(chunks), self.dimension)}, got {matrix.shape}"
            )

        created_at = datetime.now(UTC).isoformat()
        with self._lock:
            with session(self.db_path) as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM chunk WHERE book_id = ?", (book_id,))
                    conn.executemany(
                        "INSERT INTO chunk "
                        "(book_id, chapter_id, chapter_index, title, text, vector, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            (
                                book_id,
                                chapter_id,
                                chapter_index,
                                title,
                                text,
                                vector_to_blob(matrix[index]),
                                created_at,
                            )
                            for index, (chapter_id, chapter_index, title, text) in enumerate(
                                chunks
                            )
                        ],
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            self.rebuild_cache()
        return len(chunks)

    def search(
        self,
        book_id: int,
        chapter_start: int,
        chapter_end: int | None,
        query_vector: np.ndarray,
        limit: int,
    ) -> list[ScoredChunk]:
        if limit <= 0 or not self._chunks:
            return []

        query = l2_normalize(query_vector)
        with self._lock:
            chunks = self._chunks
            vectors = self._vectors

        book_ids = np.fromiter((item.book_id for item in chunks), dtype=np.int64)
        chapter_indices = np.fromiter(
            (item.chapter_index for item in chunks), dtype=np.int64
        )
        mask = (book_ids == book_id) & (chapter_indices >= chapter_start)
        if chapter_end is not None:
            mask &= chapter_indices <= chapter_end

        selected_indices = np.flatnonzero(mask)
        if selected_indices.size == 0:
            return []

        scores = vectors[selected_indices] @ query
        order = np.argsort(-scores, kind="stable")[: min(limit, selected_indices.size)]
        return [
            ScoredChunk(chunk=chunks[int(selected_indices[index])], score=float(scores[index]))
            for index in order
        ]

    def delete_book(self, book_id: int) -> None:
        with self._lock:
            with session(self.db_path) as conn:
                conn.execute("DELETE FROM chunk WHERE book_id = ?", (book_id,))
            self.rebuild_cache()

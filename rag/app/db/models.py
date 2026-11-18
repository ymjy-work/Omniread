from dataclasses import dataclass

import numpy as np

CREATE_CHUNK_TABLE = """
CREATE TABLE IF NOT EXISTS chunk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    chapter_id TEXT NOT NULL,
    chapter_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL
)
"""

CREATE_CHUNK_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chunk_book_chapter
ON chunk (book_id, chapter_index)
"""


@dataclass(frozen=True, slots=True)
class Chunk:
    id: int
    book_id: int
    chapter_id: str
    chapter_index: int
    title: str
    text: str
    vector: np.ndarray

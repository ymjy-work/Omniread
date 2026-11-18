import sqlite3

import numpy as np

from app.vectorstore.vector_db import VectorStore


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        vectors = {
            "甲": [1.0, 0.0, 0.0, 0.0],
            "乙": [0.0, 1.0, 0.0, 0.0],
            "丙": [0.0, 0.0, 1.0, 0.0],
            "丁": [0.0, 0.0, 0.0, 1.0],
        }
        return np.asarray([vectors[text] for text in texts], dtype=np.float32)


def test_filtered_dot_product_and_cache_rebuild(tmp_path) -> None:
    db_path = str(tmp_path / "rag.db")
    embeddings = FakeEmbeddings()
    store = VectorStore(db_path, 4)
    store.replace_book(
        1,
        [
            ("c1", 1, "一", "甲"),
            ("c2", 2, "二", "乙"),
            ("c5", 5, "五", "丙"),
        ],
        embeddings.embed_documents(["甲", "乙", "丙"]),
    )
    store.replace_book(
        2,
        [("x1", 1, "另一本", "丁")],
        embeddings.embed_documents(["丁"]),
    )

    query = embeddings.embed_documents(["丙"])[0]
    hits = store.search(1, 2, 5, query, 2)
    assert [hit.chunk.chapter_id for hit in hits] == ["c5", "c2"]

    reloaded = VectorStore(db_path, 4)
    assert [hit.chunk.chapter_id for hit in reloaded.search(1, 1, 1, query, 1)] == [
        "c1"
    ]


def test_index_replaces_old_chunks_and_stores_normalized_float32(tmp_path) -> None:
    db_path = str(tmp_path / "rag.db")
    embeddings = FakeEmbeddings()
    store = VectorStore(db_path, 4)
    store.replace_book(
        7,
        [("old", 1, "旧", "甲")],
        embeddings.embed_documents(["甲"]),
    )
    store.replace_book(
        7,
        [("new", 2, "新", "乙")],
        np.asarray([[3.0, 4.0, 0.0, 0.0]], dtype=np.float32),
    )

    hits = store.search(7, 1, None, np.asarray([1.0, 0.0, 0.0, 0.0]), 10)
    assert [hit.chunk.chapter_id for hit in hits] == ["new"]

    with sqlite3.connect(db_path) as conn:
        blob = conn.execute("SELECT vector FROM chunk").fetchone()[0]
    vector = np.frombuffer(blob, dtype="<f4")
    np.testing.assert_allclose(vector, [0.6, 0.8, 0.0, 0.0], rtol=1e-6)

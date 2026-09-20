"""数据层表结构：逐条对齐 M0-02 §3（离线，不连库）。

这些断言读的是 SQLAlchemy 元数据，跑单测不需要 PostgreSQL；真库上的实际形态由
`scripts/verify-data-layer.sh` 在迁移往返后核对。
"""

from __future__ import annotations

import pytest
from sqlalchemy import DateTime, Float, Integer, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql

from omniread.infrastructure.db import models
from omniread.infrastructure.db.base import Base

TABLE_NAMES = frozenset({"books", "volumes", "chapters", "chunks", "rag_runs", "chunk_mappings"})

EXPECTED_COLUMNS: dict[str, frozenset[str]] = {
    "books": frozenset({"id", "title", "author", "corpus_version", "created_at"}),
    "volumes": frozenset({"id", "book_id", "volume_index", "title", "created_at"}),
    "chapters": frozenset(
        {
            "chapter_id",
            "book_id",
            "volume_id",
            "chapter_index",
            "title",
            "source_id",
            "source_url",
            "text",
            "image_paths",
            "content_hash",
            "char_count",
            "created_at",
        }
    ),
    "chunks": frozenset(
        {
            "chunk_key",
            "book_id",
            "chapter_id",
            "chapter_index",
            "chunk_index",
            "prev_chunk_key",
            "next_chunk_key",
            "content",
            "token_count",
            "embedding",
            "content_hash",
            "chunking_version",
            "tokenizer_id",
        }
    ),
    "rag_runs": frozenset(
        {
            "run_id",
            "kind",
            "dataset_hash",
            "dataset_version",
            "corpus_manifest_hash",
            "chunking_version",
            "tokenizer_id",
            "answer_provider",
            "answer_model",
            "judge_provider",
            "judge_model",
            "embedding_provider",
            "embedding_model",
            "embedding_dim",
            "rerank_provider",
            "rerank_model",
            "prompt_version",
            "retrieval_params",
            "artifact_dir",
            "started_at",
            "finished_at",
        }
    ),
    "chunk_mappings": frozenset(
        {
            "evidence_hash",
            "chunking_version",
            "tokenizer_id",
            "mapper_model",
            "mapper_prompt_version",
            "match_status",
            "matched_chunk_key",
            "confidence",
            "overlap_reason",
            "alternative_chunk_key",
            "created_at",
        }
    ),
}


def test_table_set_is_exactly_the_frozen_six() -> None:
    assert frozenset(Base.metadata.tables) == TABLE_NAMES


def test_progress_is_not_in_this_database() -> None:
    # M0-02 §3.7：阅读进度由 Java 侧持久化，Python 库里没有这张表。
    assert "progress" not in Base.metadata.tables


@pytest.mark.parametrize("table_name", sorted(EXPECTED_COLUMNS))
def test_columns_match_spec(table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    assert frozenset(table.columns.keys()) == EXPECTED_COLUMNS[table_name]


def test_primary_keys() -> None:
    tables = Base.metadata.tables
    assert [c.name for c in tables["books"].primary_key.columns] == ["id"]
    assert [c.name for c in tables["volumes"].primary_key.columns] == ["id"]
    assert [c.name for c in tables["chapters"].primary_key.columns] == ["chapter_id"]
    assert [c.name for c in tables["chunks"].primary_key.columns] == ["chunk_key"]
    assert [c.name for c in tables["rag_runs"].primary_key.columns] == ["run_id"]
    # chunk_mappings 主键 = 五元组（M0-02 §3.6）
    assert {c.name for c in tables["chunk_mappings"].primary_key.columns} == {
        "evidence_hash",
        "chunking_version",
        "tokenizer_id",
        "mapper_model",
        "mapper_prompt_version",
    }


def test_unique_constraints() -> None:
    unique = {
        constraint.name: {col.name for col in constraint.columns}
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert unique == {
        "uq_volumes_book_id_volume_index": {"book_id", "volume_index"},
        "uq_chapters_book_id_chapter_index": {"book_id", "chapter_index"},
    }


def test_foreign_keys() -> None:
    tables = Base.metadata.tables

    def targets(table_name: str) -> set[str]:
        return {
            f"{fk.column.table.name}.{fk.column.name}"
            for fk in tables[table_name].foreign_keys
        }

    assert targets("volumes") == {"books.id"}
    assert targets("chapters") == {"books.id", "volumes.id"}
    assert targets("chunks") == {"chapters.chapter_id"}


def test_embedding_is_vector_1024() -> None:
    embedding = Base.metadata.tables["chunks"].c.embedding
    assert isinstance(embedding.type, models.Vector)
    assert embedding.type.dim == models.EMBEDDING_DIM == 1024


def test_embedding_is_nullable_for_unembedded_rows() -> None:
    # NULL 表示「尚未嵌入」，由嵌入步骤回填；回填后不应再有 NULL（迁移 0002）。
    assert Base.metadata.tables["chunks"].c.embedding.nullable is True


def test_chunks_keeps_redundant_chapter_index_for_realm_filter() -> None:
    # realm 过滤直接 WHERE chapter_index <= progress，冗余列省一次 JOIN（M0-02 §3.4 / §3.8）
    chunk_columns = Base.metadata.tables["chunks"].c
    assert isinstance(chunk_columns.chapter_index.type, Integer)
    assert isinstance(chunk_columns.chunk_index.type, Integer)


def test_chapters_image_paths_is_not_null_text_array() -> None:
    # 按章图片路径存 text[]：只整组读取、不做键查询，元素类型钉死为 text（迁移 0003）。
    column = Base.metadata.tables["chapters"].c.image_paths
    assert isinstance(column.type, postgresql.ARRAY)
    assert isinstance(column.type.item_type, Text)
    assert column.nullable is False
    assert column.server_default is not None


def test_column_types_for_key_fields() -> None:
    tables = Base.metadata.tables
    assert isinstance(tables["books"].c.id.type, Integer)
    assert isinstance(tables["books"].c.title.type, Text)
    assert isinstance(tables["chapters"].c.text.type, Text)
    assert isinstance(tables["chapters"].c.content_hash.type, Text)
    assert isinstance(tables["chunks"].c.chunking_version.type, Text)
    assert isinstance(tables["chunks"].c.tokenizer_id.type, Text)
    assert isinstance(tables["rag_runs"].c.embedding_dim.type, Integer)
    assert isinstance(tables["rag_runs"].c.prompt_version.type, Text)
    assert isinstance(tables["chunk_mappings"].c.confidence.type, Float)
    for column in ("started_at", "finished_at", "created_at"):
        table = tables["rag_runs"] if column != "created_at" else tables["chapters"]
        column_type = table.c[column].type
        assert isinstance(column_type, DateTime)
        assert column_type.timezone is True


def test_hnsw_index_has_explicit_build_parameters() -> None:
    chunks = Base.metadata.tables["chunks"]
    hnsw = next(index for index in chunks.indexes if index.name == "ix_chunks_embedding_hnsw")
    options = hnsw.dialect_options["postgresql"]
    assert options["using"] == "hnsw"
    assert options["with"] == {"m": 16, "ef_construction": 64}
    assert options["ops"] == {"embedding": "vector_cosine_ops"}


def test_plain_indexes_for_realm_and_neighbor_lookups() -> None:
    tables = Base.metadata.tables
    chapter_indexes = {index.name for index in tables["chapters"].indexes}
    chunk_indexes = {index.name for index in tables["chunks"].indexes}
    assert "ix_chapters_book_id_chapter_index" in chapter_indexes
    assert "ix_chunks_chapter_id_chunk_index" in chunk_indexes


def test_runtime_hnsw_gucs_cover_dense_k() -> None:
    from omniread.infrastructure.db.session import HNSW_SESSION_SETTINGS

    # dense_k = 60，pgvector 默认 ef_search = 40；会话参数必须显式覆盖默认值（M0-01 §4.2）
    joined = " ".join(HNSW_SESSION_SETTINGS)
    assert "hnsw.iterative_scan = relaxed_order" in joined
    assert "hnsw.max_scan_tuples = 20000" in joined
    assert "hnsw.ef_search = 100" in joined

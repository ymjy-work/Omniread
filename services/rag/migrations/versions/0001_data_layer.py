"""M0 数据层：books / volumes / chapters / chunks / rag_runs / chunk_mappings

Revision ID: 0001_data_layer
Revises:
Create Date: 2026-09-19

表结构照 M0-02 §3 逐列建。`progress`（阅读进度）不在这里——它由 Java 侧持久化（§3.7）。

content_hash 口径（P-3 最小规范化，与 checksums.json 同函数 `omniread.domain.text`）：
统一换行为 `\\n`、逐行去行尾空白，再对 UTF-8 字节取 sha256 小写十六进制；
`[插图NNN]` 占位符保留，全半角与标点不动。章节正文与 checksums.json 的逐章 hash 必须
调用同一函数计算，否则两个产物的 hash 对不上。

pgvector 运行时参数（hnsw.iterative_scan / hnsw.max_scan_tuples / hnsw.ef_search）
不写在本迁移里：它们是会话级 GUC，落点在连接层
`omniread.infrastructure.db.session.create_engine_from_env`，理由见该模块注释。
本迁移只负责建扩展、建表与建向量索引。

downgrade 不删 vector 扩展：同一集群可能有别的库共用它。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_data_layer"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与建模侧同值（models.py）；写死在迁移里，避免应用代码变化改写已发布迁移的语义。
_EMBEDDING_DIM = 1024
_HNSW_M = 16
_HNSW_EF_CONSTRUCTION = 64

_NOW = sa.text("now()")


def upgrade() -> None:
    # pgvector 镜像只带扩展文件，不会自动 CREATE EXTENSION；vector 类型必须先就位。
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("corpus_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_books"),
    )

    op.create_table(
        "volumes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("volume_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], name="fk_volumes_book_id_books"),
        sa.PrimaryKeyConstraint("id", name="pk_volumes"),
        sa.UniqueConstraint("book_id", "volume_index", name="uq_volumes_book_id_volume_index"),
    )

    op.create_table(
        "chapters",
        sa.Column("chapter_id", sa.Text(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("volume_id", sa.Integer(), nullable=False),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], name="fk_chapters_book_id_books"),
        sa.ForeignKeyConstraint(
            ["volume_id"], ["volumes.id"], name="fk_chapters_volume_id_volumes"
        ),
        sa.PrimaryKeyConstraint("chapter_id", name="pk_chapters"),
        sa.UniqueConstraint("book_id", "chapter_index", name="uq_chapters_book_id_chapter_index"),
    )
    # 普通索引：章节列表按 (book_id, chapter_index) 检索（M0-02 §3.8）。
    op.create_index("ix_chapters_book_id_chapter_index", "chapters", ["book_id", "chapter_index"])

    op.create_table(
        "chunks",
        sa.Column("chunk_key", sa.Text(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Text(), nullable=False),
        # 冗余列：realm 过滤 `chapter_index <= progress` 直接用它，避免每次 JOIN。
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("prev_chunk_key", sa.Text(), nullable=True),
        sa.Column("next_chunk_key", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("chunking_version", sa.Text(), nullable=False),
        sa.Column("tokenizer_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chapter_id"], ["chapters.chapter_id"], name="fk_chunks_chapter_id_chapters"
        ),
        sa.PrimaryKeyConstraint("chunk_key", name="pk_chunks"),
    )
    op.create_index("ix_chunks_chapter_id_chunk_index", "chunks", ["chapter_id", "chunk_index"])

    # 构建参数显式写出，避免被非默认参数污染（M0-01 §4.2）。
    # 距离度量用余弦：文本向量检索的通行口径；换成别的算子需要重建索引。
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) "
        f"WITH (m = {_HNSW_M}, ef_construction = {_HNSW_EF_CONSTRUCTION})"
    )

    op.create_table(
        "rag_runs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("dataset_hash", sa.Text(), nullable=False),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("corpus_manifest_hash", sa.Text(), nullable=False),
        sa.Column("chunking_version", sa.Text(), nullable=False),
        sa.Column("tokenizer_id", sa.Text(), nullable=False),
        sa.Column("answer_provider", sa.Text(), nullable=False),
        sa.Column("answer_model", sa.Text(), nullable=False),
        sa.Column("judge_provider", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.Text(), nullable=False),
        sa.Column("embedding_provider", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("rerank_provider", sa.Text(), nullable=False),
        sa.Column("rerank_model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("retrieval_params", JSONB(), nullable=False),
        sa.Column("artifact_dir", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_id", name="pk_rag_runs"),
    )

    op.create_table(
        "chunk_mappings",
        sa.Column("evidence_hash", sa.Text(), nullable=False),
        sa.Column("chunking_version", sa.Text(), nullable=False),
        sa.Column("tokenizer_id", sa.Text(), nullable=False),
        sa.Column("mapper_model", sa.Text(), nullable=False),
        sa.Column("mapper_prompt_version", sa.Text(), nullable=False),
        sa.Column("match_status", sa.Text(), nullable=False),
        sa.Column("matched_chunk_key", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("overlap_reason", sa.Text(), nullable=False),
        sa.Column("alternative_chunk_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint(
            "evidence_hash",
            "chunking_version",
            "tokenizer_id",
            "mapper_model",
            "mapper_prompt_version",
            name="pk_chunk_mappings",
        ),
    )


def downgrade() -> None:
    # 先删向量索引，再按外键依赖逆序删表。扩展保留（见模块 docstring）。
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index("ix_chunks_chapter_id_chunk_index", table_name="chunks")

    op.drop_table("chunk_mappings")
    op.drop_table("rag_runs")
    op.drop_table("chunks")
    op.drop_index("ix_chapters_book_id_chapter_index", table_name="chapters")
    op.drop_table("chapters")
    op.drop_table("volumes")
    op.drop_table("books")

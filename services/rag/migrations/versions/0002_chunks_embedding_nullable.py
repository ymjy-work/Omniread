"""chunks.embedding 可空：NULL 表示「尚未嵌入」

Revision ID: 0002_chunks_embedding_nullable
Revises: 0001_data_layer
Create Date: 2026-09-19

导入阶段先落 NULL、向量由嵌入步骤批量回填，因此该列必须可空。

不给零向量占位：零向量在余弦距离下与任何向量的距离都是 0，会照常参与排序并挤占结果；
而漏嵌几条时不会有任何报错，缺向量反而被淹没。

NULL 的语义固定为「尚未嵌入」，只有这一个含义。检索侧必须显式识别这一点——读向量列前按
`embedding IS NOT NULL` 过滤（或先断言该表无 NULL），否则距离比较会得到 NULL、
静默漏召回。

downgrade 改回 NOT NULL；若此时表里已有 NULL，PostgreSQL 会拒绝执行并报错。
这是有意的硬失败：把「尚未嵌入」静默写成假向量或直接删行，都会让回滚看起来成功而数据已经错了。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0002_chunks_embedding_nullable"
down_revision: str | None = "0001_data_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与迁移 0001 / 建模侧同值（M0-01 §4.2）；向量维度是单向门，只用于 ALTER 的类型比对。
_EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(_EMBEDDING_DIM),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(_EMBEDDING_DIM),
        existing_nullable=True,
        nullable=False,
    )

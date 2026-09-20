"""M0 数据层的 SQLAlchemy 模型：字段逐列照 `M0-02-数据结构设计.md` §3 建。

表集合固定为 `books` / `volumes` / `chapters` / `chunks` / `rag_runs` / `chunk_mappings`。
阅读进度 `progress` **不进本库**——它由 Java 侧持久化后随请求传入（M0-02 §3.7）。

向量维度与 HNSW 参数是单向门：`embedding` 固定 `vector(1024)`，构建参数固定 `m=16` /
`ef_construction=64`。改维度要重建该列并重跑全量索引；参数写在模型与迁移里同一份常量上，
避免两处各写一个数。
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)

# `Chapter.text` 是列属性，类体里裸用 `text(...)` 会被它遮蔽，这里以别名引入。
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from omniread.infrastructure.db.base import Base

# 已冻结（M0-02 §3.4 / §3.8，M0-01 §4.2）：向量维度与 HNSW 构建参数。
EMBEDDING_DIM = 1024
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64

# 索引算子类：文本 embedding 取余弦距离；HNSW 查询必须用与索引一致的算子才能命中索引。
HNSW_OPS = "vector_cosine_ops"


def _created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Book(Base):
    __tablename__ = "books"

    # M0 恒为 1，不依赖自增
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    # 语料版本；变更即新基线（M0-02 §7.3）
    corpus_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at_column()


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (
        UniqueConstraint("book_id", "volume_index", name="uq_volumes_book_id_volume_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False)
    # 卷在语料中的首次出现次序，1..15；语料目录顺序不是阅读顺序，必须显式存
    volume_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at_column()


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("book_id", "chapter_index", name="uq_chapters_book_id_chapter_index"),
        Index("ix_chapters_book_id_chapter_index", "book_id", "chapter_index"),
    )

    # 形如 book:{book_id}:chapter:{chapter_index}；不用自增 ID，跨环境重导要稳定可复现
    chapter_id: Mapped[str] = mapped_column(Text, primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False)
    volume_id: Mapped[int] = mapped_column(Integer, ForeignKey("volumes.id"), nullable=False)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    # 章节正文副本；服务端读 DB 即可，不必每次去对象存储取
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # 语料内图片相对路径（`images/01_第1卷/007.jpg`），顺序即语料里的出现顺序。
    # 目录接口据此重建 `[插图NNN]` 的 marker→url 映射（M0-02 §2）；路径是字符串数组，
    # 用 text[] 而不是 jsonb：只整组读取、不做键查询，数组元素类型还能钉死为 text。
    image_paths: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa_text("'{}'::text[]")
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _created_at_column()


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_chapter_id_chunk_index", "chapter_id", "chunk_index"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": HNSW_M, "ef_construction": HNSW_EF_CONSTRUCTION},
            postgresql_ops={"embedding": HNSW_OPS},
        ),
    )

    # 形如 {chapter_id}#c{chunk_index}
    chunk_key: Mapped[str] = mapped_column(Text, primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_id: Mapped[str] = mapped_column(Text, ForeignKey("chapters.chapter_id"), nullable=False)
    # 冗余列：realm 过滤直接在 WHERE 上用 chapter_index <= progress，省一次 JOIN
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # 只指向同章邻居，chunk 不跨章
    prev_chunk_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_chunk_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # 可空：NULL 表示「尚未嵌入」，由嵌入步骤回填；回填后不应再有 NULL。
    # 不写零向量占位——零向量在余弦距离下会照常参与排序，且漏嵌不会被发现。
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # 切片 profile 标识，与 chunk_mappings.chunking_version 取同值
    chunking_version: Mapped[str] = mapped_column(Text, nullable=False)
    # 只承载身份 `实现名:编码/模型名:版本`，误差值存 profile 元数据
    tokenizer_id: Mapped[str] = mapped_column(Text, nullable=False)


class RagRun(Base):
    __tablename__ = "rag_runs"

    # 形如 2026-09-17-m0-baseline；目录名与 DB 记录共用
    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_hash: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    corpus_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    chunking_version: Mapped[str] = mapped_column(Text, nullable=False)
    tokenizer_id: Mapped[str] = mapped_column(Text, nullable=False)
    # 换回答 / judge / embedding / rerank 模型或维度均即新基线（M0-02 §7.3）
    answer_provider: Mapped[str] = mapped_column(Text, nullable=False)
    answer_model: Mapped[str] = mapped_column(Text, nullable=False)
    judge_provider: Mapped[str] = mapped_column(Text, nullable=False)
    judge_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_provider: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    rerank_provider: Mapped[str] = mapped_column(Text, nullable=False)
    rerank_model: Mapped[str] = mapped_column(Text, nullable=False)
    # 答案 prompt 模板内容的 sha256 短串；语义变更即新基线
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # RRF_K / dense_k / kw_k / rerank_k / ask_* 等
    retrieval_params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    artifact_dir: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChunkMapping(Base):
    __tablename__ = "chunk_mappings"

    # 主键 = 五元组；任一分量变更即失效，改映射 prompt 或换 mapper 模型必须显式 purge
    evidence_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    chunking_version: Mapped[str] = mapped_column(Text, primary_key=True)
    tokenizer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mapper_model: Mapped[str] = mapped_column(Text, primary_key=True)
    mapper_prompt_version: Mapped[str] = mapped_column(Text, primary_key=True)
    # matched / low_conf / unmatched
    match_status: Mapped[str] = mapped_column(Text, nullable=False)
    matched_chunk_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    overlap_reason: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_chunk_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at_column()

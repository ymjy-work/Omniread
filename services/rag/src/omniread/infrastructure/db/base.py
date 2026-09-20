"""SQLAlchemy 声明式基类与索引 / 约束命名约定。

命名约定固定下来，是为了让迁移里的 DROP / ALTER 能按名字定位对象，
而不是依赖数据库生成的随机名（`chunks_chapter_id_fkey` 这类默认名在不同环境下不稳定）。
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

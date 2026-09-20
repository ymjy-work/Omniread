"""Alembic 运行环境。

连接串从环境变量装配（`omniread.infrastructure.db.session.database_url`），
不读 `alembic.ini` 里的 `sqlalchemy.url`——含口令的串不落盘。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from omniread.infrastructure.db import models  # noqa: F401  导入以注册全部表到 metadata
from omniread.infrastructure.db.base import Base
from omniread.infrastructure.db.session import database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# configparser 会把 % 当插值起始符，连接串里的 % 需要转义后再写入。
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 迁移不挂 HNSW 会话参数监听：全新库的 vector 扩展由迁移第一步建，
    # 连接建立时扩展尚不存在，监听会在建扩展之前就失败。
    connectable = create_engine(config.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

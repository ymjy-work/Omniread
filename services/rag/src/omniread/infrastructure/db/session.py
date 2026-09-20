"""数据库连接：从环境变量装配 URL，并在每条连接上设置 pgvector 的 HNSW 会话参数。

凭据只从环境变量读，不写默认值、不落盘（M0-00 §6）。非凭据项（主机 / 端口 / 库名 / 用户）
给与 `infra/docker/docker-compose.yml` 一致的默认值，便于本机直接使用；口令没有默认值，
缺失即显式失败，不做静默降级。
"""

from __future__ import annotations

import os
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, event

# pgvector 运行时参数（M0-01 §4.2 / M0-02 §3.8）。
#
# 落点选「连接建立时 SET」而不是迁移里的 ALTER DATABASE / ROLE SET：
# 这三项是会话级 GUC，随连接生命周期走；定在连接层则应用进程、评测 runner、
# 一次性脚本只要走本模块建引擎就自动带上，不必依赖某个库名，也不会把设置
# 遗留给共用同一集群的其他库。代价是连接建立时要求 vector 扩展已存在——
# 迁移负责建扩展，所以引擎只在迁移之后使用。
#
# hnsw.iterative_scan = relaxed_order：过滤条件无法下推进 HNSW 索引内部，
#   realm 收窄时候选集过小会导致召回不齐，必须开迭代扫描。
# hnsw.ef_search = 100：dense_k=60 而 pgvector 默认 40，默认值下召不满候选。
HNSW_SESSION_SETTINGS: tuple[str, ...] = (
    "SET hnsw.iterative_scan = relaxed_order",
    "SET hnsw.max_scan_tuples = 20000",
    "SET hnsw.ef_search = 100",
)


def database_url() -> str:
    """从环境变量装配 psycopg 连接串；缺 `POSTGRES_PASSWORD` 即抛错。"""
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError("POSTGRES_PASSWORD 未注入：数据库凭据只从环境变量读，不设默认值")
    user = os.environ.get("POSTGRES_USER", "omniread")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "55432")
    name = os.environ.get("POSTGRES_DB", "omniread")
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{name}"
    )


def _apply_hnsw_session_settings(dbapi_connection: object, _record: object) -> None:
    """连接建立时下发 HNSW 会话参数。

    `SET` 会话级生效并跨事务存活，这里提交一次事务让参数不必等到首次业务查询才生效。
    `vector` 扩展缺失时 `SET hnsw.*` 会报 unrecognized configuration parameter——
    这是有意的显式失败：参数没设上的检索会静默少召回，比直接报错危险得多。
    """
    with dbapi_connection.cursor() as cursor:  # type: ignore[attr-defined]
        for statement in HNSW_SESSION_SETTINGS:
            cursor.execute(statement)
    dbapi_connection.commit()  # type: ignore[attr-defined]


def create_engine_from_env(*, echo: bool = False) -> Engine:
    """按环境变量建引擎，并挂上 HNSW 会话参数监听。"""
    engine = create_engine(database_url(), pool_pre_ping=True, echo=echo)
    event.listen(engine, "connect", _apply_hnsw_session_settings)
    return engine

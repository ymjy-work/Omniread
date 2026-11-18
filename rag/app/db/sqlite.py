import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.db.models import CREATE_CHUNK_INDEX, CREATE_CHUNK_TABLE


def connect(path: str) -> sqlite3.Connection:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def session(path: str) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize(path: str) -> None:
    with session(path) as conn:
        conn.execute(CREATE_CHUNK_TABLE)
        conn.execute(CREATE_CHUNK_INDEX)

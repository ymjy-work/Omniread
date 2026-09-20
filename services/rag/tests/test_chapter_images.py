"""按章图片：marker→url 重建，以及 image_paths 在真库上的落库往返。

marker / url 的推导是不碰库的纯函数，离线也要跑；落库往返需要 PostgreSQL——
未注入 `POSTGRES_PASSWORD` 时跳过（与正式语料相关的测试同一惯例），
注入了就真读写一次、事务回滚，不留残留行。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session, sessionmaker

from omniread.domain.models import ImageRef
from omniread.infrastructure.db.catalog import PgCatalogRepository, build_image_refs
from omniread.infrastructure.db.models import Book, Chapter, Volume

# 真库往返用的假 book_id：避开正式数据（book_id=1），事务回滚后不留下任何行。
TEST_BOOK_ID = 987654


def test_marker_is_file_stem_aligned_with_illustration_number() -> None:
    refs = build_image_refs(1, ["images/01_第1卷/007.jpg"])

    # 文件主干 "007" 与正文里的 [插图007] 编号对齐，前导零保留。
    assert refs == (
        ImageRef(marker="007", url="/api/v1/books/1/images/01_第1卷/007.jpg"),
    )


def test_url_drops_corpus_images_prefix_and_keeps_book_scoped_path() -> None:
    [ref] = build_image_refs(3, ["images/短篇/012.png"])

    assert ref.marker == "012"
    assert ref.url == "/api/v1/books/3/images/短篇/012.png"
    assert "images/images/" not in ref.url


def test_multiple_images_keep_corpus_order() -> None:
    refs = build_image_refs(
        1, ["images/02_第2卷/002.jpg", "images/02_第2卷/001.jpg"]
    )

    assert [ref.marker for ref in refs] == ["002", "001"]


def test_chapter_without_images_returns_empty_array() -> None:
    assert build_image_refs(1, []) == ()


@pytest.fixture
def chapter_session() -> Iterator[tuple[Session, PgCatalogRepository]]:
    if not os.environ.get("POSTGRES_PASSWORD"):
        pytest.skip("未注入 POSTGRES_PASSWORD，跳过真库往返")

    from omniread.infrastructure.db.session import create_engine_from_env

    engine = create_engine_from_env()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    repository = PgCatalogRepository(sessionmaker(bind=connection))
    try:
        yield session, repository
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _seed_book_with_volume(session: Session) -> int:
    session.execute(
        insert(Book).values(
            id=TEST_BOOK_ID, title="测试书", author="测试作者", corpus_version="corpus-test"
        )
    )
    return session.execute(
        insert(Volume)
        .values(book_id=TEST_BOOK_ID, volume_index=1, title="第一卷")
        .returning(Volume.id)
    ).scalar_one()


def _seed_chapter(
    session: Session, volume_id: int, chapter_index: int, image_paths: list[str]
) -> None:
    session.execute(
        insert(Chapter).values(
            chapter_id=f"book:{TEST_BOOK_ID}:chapter:{chapter_index}",
            book_id=TEST_BOOK_ID,
            volume_id=volume_id,
            chapter_index=chapter_index,
            title=f"第{chapter_index}话",
            source_id=f"src-{chapter_index}",
            source_url=f"https://example.invalid/{chapter_index}",
            text="正文[插图007]\n",
            image_paths=image_paths,
            content_hash="hash",
            char_count=9,
        )
    )
    session.flush()


def _clear(session: Session) -> None:
    session.execute(delete(Chapter).where(Chapter.book_id == TEST_BOOK_ID))
    session.execute(delete(Volume).where(Volume.book_id == TEST_BOOK_ID))
    session.execute(delete(Book).where(Book.id == TEST_BOOK_ID))


def test_image_paths_round_trip_and_get_chapter_rebuilds_refs(
    chapter_session: tuple[Session, PgCatalogRepository],
) -> None:
    session, repository = chapter_session
    _clear(session)
    volume_id = _seed_book_with_volume(session)
    _seed_chapter(session, volume_id, 1, ["images/01_第1卷/007.jpg"])
    _seed_chapter(session, volume_id, 2, [])

    stored = repository.get_chapter(TEST_BOOK_ID, 1)
    assert stored is not None
    assert stored.images == (
        ImageRef(marker="007", url="/api/v1/books/987654/images/01_第1卷/007.jpg"),
    )

    # 无图章返回空数组，不是 None。
    empty = repository.get_chapter(TEST_BOOK_ID, 2)
    assert empty is not None
    assert empty.images == ()


def test_image_paths_are_replaced_on_reimport(
    chapter_session: tuple[Session, PgCatalogRepository],
) -> None:
    session, repository = chapter_session
    _clear(session)
    volume_id = _seed_book_with_volume(session)
    _seed_chapter(session, volume_id, 1, ["images/01_第1卷/007.jpg", "images/01_第1卷/008.jpg"])

    # 整批替换语义：先删后重写，重写后图片路径是新值（导入幂等的 DB 侧证据）。
    session.execute(delete(Chapter).where(Chapter.book_id == TEST_BOOK_ID))
    _seed_chapter(session, volume_id, 1, ["images/03_第3卷/020.jpg"])

    stored = repository.get_chapter(TEST_BOOK_ID, 1)
    assert stored is not None
    assert [ref.marker for ref in stored.images] == ["020"]
    assert [ref.url for ref in stored.images] == [
        "/api/v1/books/987654/images/03_第3卷/020.jpg"
    ]

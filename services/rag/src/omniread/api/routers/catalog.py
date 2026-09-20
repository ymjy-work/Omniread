"""catalog 路由：书列表、章节列表、章节详情、插图。

`book_id` / `chapter_index` 的 realm 合法性由 Java 在 API 边界校验，
本服务不重复校验；这里只做路径层面的形状校验。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Response

from omniread.api.deps import get_catalog, get_image_storage
from omniread.api.schemas import (
    Book,
    BookList,
    ChapterDetail,
    ChapterList,
    ChapterSummaryBody,
    ErrorBody,
)
from omniread.application.ports import CatalogRepository, ImageStorage
from omniread.domain.errors import ResourceNotFound
from omniread.infrastructure.objectstore.paths import resolve_image_key

router = APIRouter(tags=["catalog"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorBody, "description": "资源不存在"}
}
_NOT_FOUND_OR_BAD_PATH: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorBody, "description": "资源不存在"},
    400: {"model": ErrorBody, "description": "路径非法"},
}


@router.get("/books", response_model=BookList, operation_id="internalListBooks")
def list_books(catalog: CatalogRepository = Depends(get_catalog)) -> BookList:
    return BookList(books=[Book.model_validate(asdict(book)) for book in catalog.list_books()])


@router.get(
    "/books/{book_id}/chapters",
    response_model=ChapterList,
    operation_id="internalListChapters",
)
def list_chapters(
    book_id: int, catalog: CatalogRepository = Depends(get_catalog)
) -> ChapterList:
    chapters = [
        ChapterSummaryBody.model_validate(asdict(chapter))
        for chapter in catalog.list_chapters(book_id)
    ]
    return ChapterList(book_id=book_id, chapters=chapters)


@router.get(
    "/books/{book_id}/chapters/{chapter_index}",
    response_model=ChapterDetail,
    operation_id="internalGetChapter",
    responses=_NOT_FOUND,
)
def get_chapter(
    book_id: int, chapter_index: int, catalog: CatalogRepository = Depends(get_catalog)
) -> ChapterDetail:
    detail = catalog.get_chapter(book_id, chapter_index)
    if detail is None:
        raise ResourceNotFound("章节不存在")
    return ChapterDetail.model_validate(asdict(detail))


@router.get(
    "/books/{book_id}/images/{path:path}",
    operation_id="internalGetImage",
    responses=_NOT_FOUND_OR_BAD_PATH,
    response_class=Response,
)
def get_image(
    book_id: int, path: str, storage: ImageStorage = Depends(get_image_storage)
) -> Response:
    # 路径来自客户端：先过目录穿越与扩展名白名单，再去对象存储取。
    key = resolve_image_key(book_id, path)
    stored = storage.get(key)
    if stored is None:
        raise ResourceNotFound("图片不存在")
    return Response(content=stored.data, media_type=stored.content_type)

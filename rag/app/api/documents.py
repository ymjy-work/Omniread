from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_pipeline
from app.schemas import IndexRequest, IndexResponse

router = APIRouter(tags=["documents"])


@router.post("/v1/index", response_model=IndexResponse)
async def index_book(
    request: IndexRequest,
    pipeline: Annotated[Any, Depends(get_pipeline)],
) -> IndexResponse:
    return await pipeline.index(request)

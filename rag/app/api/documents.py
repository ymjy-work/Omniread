from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["documents"])


@router.post("/v1/index")
async def index_book() -> None:
    # 契约见 .agent/docs/Omniread架构.md §5
    raise HTTPException(status_code=501, detail="not implemented")

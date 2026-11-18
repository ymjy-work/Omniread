from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["rag"])


@router.post("/v1/ask")
async def ask() -> None:
    # 契约见 .agent/docs/Omniread架构.md §5
    raise HTTPException(status_code=501, detail="not implemented")

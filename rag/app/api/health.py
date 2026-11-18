from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

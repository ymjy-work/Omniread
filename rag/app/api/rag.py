from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_pipeline
from app.rag.pipeline import ModelGenerationError
from app.rag.realm import InvalidRealmError
from app.schemas import AskRequest, AskResponse

router = APIRouter(tags=["rag"])


@router.post("/v1/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    pipeline: Annotated[Any, Depends(get_pipeline)],
) -> AskResponse:
    try:
        return await pipeline.ask(request)
    except InvalidRealmError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
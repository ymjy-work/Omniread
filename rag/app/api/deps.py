from typing import Any

from fastapi import HTTPException, Request


def get_pipeline(request: Request) -> Any:
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="RAG pipeline is not ready")
    return pipeline

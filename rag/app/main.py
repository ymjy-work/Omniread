from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api import documents, health, rag
from app.rag.pipeline import RagPipeline


def create_app(pipeline: Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.pipeline is None:
            app.state.pipeline = RagPipeline()
        yield

    application = FastAPI(
        title="Omniread RAG",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.pipeline = pipeline
    application.include_router(health.router)
    application.include_router(documents.router)
    application.include_router(rag.router)
    return application


app = create_app()

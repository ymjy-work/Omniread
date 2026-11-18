from fastapi import FastAPI

from app.api import documents, health, rag

app = FastAPI(title="Omniread RAG", version="0.1.0")

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(rag.router)

from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import init_db
from app.api import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="RAG Knowledge QA", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}

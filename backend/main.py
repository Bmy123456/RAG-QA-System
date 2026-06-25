"""
FastAPI 入口：注册路由、中间件、启动初始化。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.db.session import init_db
from backend.api.knowledge_base import router as kb_router
from backend.api.chat import router as chat_router
from backend.api.evaluation import router as eval_router
from backend.api.auth import router as auth_router
from backend.api.admin import router as admin_router
from backend.api.dashboard import router as dashboard_router
from backend.middleware.metrics import MetricsMiddleware
import backend.models  # noqa: F401  # 确保所有 ORM 表注册

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库。"""
    init_db()
    yield


app = FastAPI(
    title="RAG 智能问答系统",
    description="基于检索增强生成的多用户知识库问答系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP 请求指标中间件
app.add_middleware(MetricsMiddleware)

# 注册路由
app.include_router(auth_router)
app.include_router(kb_router)
app.include_router(chat_router)
app.include_router(eval_router)
app.include_router(admin_router)
app.include_router(dashboard_router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# 托管前端静态文件（生产模式）
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA 回退：非 API 路径统一返回 index.html。"""
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")

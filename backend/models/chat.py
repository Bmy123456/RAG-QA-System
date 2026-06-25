"""
对话相关的 Pydantic 请求/响应模型（供 API 层使用）。
"""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    kb_id: int | None = None
    session_id: str | None = None
    strategy: str = "hybrid"
    top_k: int | None = None
    stream: bool = True


class SourceResponse(BaseModel):
    index: int
    chunk_id: str
    filename: str
    page: int | None
    snippet: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[SourceResponse]
    rewritten_query: str | None = None
    model: str

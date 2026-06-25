"""
对话 API：发送消息（SSE 流式/非流式）、获取历史、清空会话。

所有接口需要登录。会话与用户绑定，用户只能查看自己的历史。
编排流程：用户问题 → 问题改写 → 检索 → 重排序 → 生成回答 → 返回
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config.settings import (
    EMBEDDING_CONFIG, EMBEDDING_CACHE_CONFIG, VECTOR_STORE_CONFIG,
    RERANKER_CONFIG, RETRIEVAL_CONFIG, CONVERSATION_CONFIG, GENERATOR_CONFIG,
    QA_LOGGING_ENABLED,
)
from backend.db.crud import get_kb
from backend.db.session import get_db
from backend.api.evaluation import get_query_logger
from backend.api.auth import require_user
from backend.models.user import User

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

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


class HistoryResponse(BaseModel):
    session_id: str
    kb_id: int
    messages: list[dict]


# ---------------------------------------------------------------------------
# 全局实例（延迟初始化）
# ---------------------------------------------------------------------------

_conversation_manager = None
_embedding_service = None
_vector_store = None
_retriever = None
_reranker = None
_generator = None


def _get_conversation_manager():
    global _conversation_manager
    if _conversation_manager is None:
        from backend.core.conversation import ConversationManager
        _conversation_manager = ConversationManager(CONVERSATION_CONFIG)
    return _conversation_manager


def _get_embedding_service():
    global _embedding_service
    if _embedding_service is None:
        from backend.core.embedding import EmbeddingService
        _embedding_service = EmbeddingService(
            provider=EMBEDDING_CONFIG["provider"],
            config=EMBEDDING_CONFIG,
            cache_config=EMBEDDING_CACHE_CONFIG,
        )
    return _embedding_service


def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        from backend.core.vector_store import create_vector_store
        _vector_store = create_vector_store(
            VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG,
        )
    return _vector_store


def _get_retriever():
    global _retriever
    if _retriever is None:
        from backend.core.retrieval import HybridRetriever
        from backend.db.session import SessionLocal
        _retriever = HybridRetriever(
            vector_store=_get_vector_store(),
            embedding_service=_get_embedding_service(),
            config={
                "initial_top_k": RETRIEVAL_CONFIG["initial_top_k"],
                "final_top_k": RETRIEVAL_CONFIG["final_top_k"],
                "bm25_db_session_factory": SessionLocal,
            },
        )
    return _retriever


def _get_reranker():
    global _reranker
    if _reranker is None:
        from backend.core.reranker import create_reranker
        _reranker = create_reranker(
            RERANKER_CONFIG["provider"], RERANKER_CONFIG,
        )
    return _reranker


def _get_generator():
    global _generator
    if _generator is None:
        from backend.core.generator import AnswerGenerator
        _generator = AnswerGenerator(GENERATOR_CONFIG)
    return _generator


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _check_session_owner(session, user: User):
    """校验会话归属：只能操作自己的会话，管理员可操作所有。"""
    if session.user_id and session.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权操作此会话")


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@router.post("")
async def chat(
    data: ChatRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """发送消息，返回答案+引用（支持 SSE 流式）。"""

    # 验证知识库访问权限
    if data.kb_id is not None:
        kb = get_kb(db, data.kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if not kb.is_public and kb.user_id != user.id and user.role != "admin":
            raise HTTPException(status_code=403, detail="无权访问此知识库")

    conv_mgr = _get_conversation_manager()

    # 创建或获取会话
    if data.session_id:
        session = await conv_mgr.get_session(data.session_id)
        if not session:
            session = await conv_mgr.create_session(data.kb_id or 0, user_id=user.id)
        else:
            _check_session_owner(session, user)
    else:
        session = await conv_mgr.create_session(data.kb_id or 0, user_id=user.id)

    session_id = session.session_id

    # 问题改写
    search_query, original_query, was_rewritten = await conv_mgr.process_query(
        data.question, session_id,
    )

    # 检索
    retriever = _get_retriever()
    from backend.core.vector_store import SearchFilter
    search_filter = SearchFilter(kb_id=data.kb_id) if data.kb_id else None

    retrieval_results = await retriever.retrieve(
        query=search_query,
        search_filter=search_filter,
        top_k=RETRIEVAL_CONFIG["initial_top_k"],
        strategy=data.strategy,
    )

    # 重排序
    if retrieval_results:
        reranker = _get_reranker()
        from backend.core.reranker import RerankInput
        rerank_inputs = [RerankInput.from_retrieval_result(r) for r in retrieval_results]
        final_top_k = data.top_k or RETRIEVAL_CONFIG["final_top_k"]
        rerank_results = await reranker.rerank(search_query, rerank_inputs, top_k=final_top_k)
    else:
        rerank_results = []

    # 获取截断后的历史
    history = await conv_mgr.get_truncated_history(session_id)
    history_dicts = [{"role": m.role, "content": m.content} for m in history]

    # 生成回答
    generator = _get_generator()
    start_time = time.time()

    if data.stream:
        return StreamingResponse(
            _stream_response(
                generator=generator,
                question=original_query,
                documents=rerank_results,
                history=history_dicts,
                session_id=session_id,
                conv_mgr=conv_mgr,
                rewritten_query=search_query if was_rewritten else None,
                user_id=user.id,
                kb_id=data.kb_id,
                strategy=data.strategy,
                retrieval_count=len(retrieval_results),
                reranked_count=len(rerank_results),
                db=db,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Session-Id": session_id,
            },
        )
    else:
        result = await generator.generate(
            question=original_query,
            documents=rerank_results,
            history=history_dicts,
        )

        await conv_mgr.add_assistant_message(
            session_id, result.answer,
            metadata={"sources": [asdict(s) for s in result.sources]},
        )

        latency_ms = int((time.time() - start_time) * 1000)
        if QA_LOGGING_ENABLED:
            logger = get_query_logger()
            logger.log(db, {
                "session_id": session_id,
                "user_id": user.id,
                "kb_id": data.kb_id,
                "question": original_query,
                "rewritten_query": search_query if was_rewritten else None,
                "answer": result.answer,
                "sources_json": json.dumps([asdict(s) for s in result.sources], ensure_ascii=False),
                "model": result.model,
                "latency_ms": latency_ms,
                "token_prompt": result.token_usage.get("prompt", 0),
                "token_completion": result.token_usage.get("completion", 0),
                "token_total": result.token_usage.get("total", 0),
                "retrieval_strategy": data.strategy,
                "retrieval_count": len(retrieval_results),
                "reranked_count": len(rerank_results),
            })

        return ChatResponse(
            session_id=session_id,
            answer=result.answer,
            sources=[
                SourceResponse(
                    index=s.index, chunk_id=s.chunk_id,
                    filename=s.filename, page=s.page, snippet=s.snippet,
                )
                for s in result.sources
            ],
            rewritten_query=search_query if was_rewritten else None,
            model=result.model,
        )


async def _stream_response(
    generator,
    question: str,
    documents: list,
    history: list[dict],
    session_id: str,
    conv_mgr,
    rewritten_query: str | None,
    user_id: int,
    kb_id: int | None,
    strategy: str,
    retrieval_count: int,
    reranked_count: int,
    db: Session,
):
    """SSE 流式输出生成器。"""
    from backend.db.session import SessionLocal

    full_answer = ""
    sources_data = []
    start_time = time.time()

    try:
        async for chunk in generator.generate_stream(question, documents, history):
            if chunk.startswith("__SOURCES__"):
                raw = chunk[len("__SOURCES__"):]
                try:
                    sources_data = json.loads(raw)
                except json.JSONDecodeError:
                    sources_data = []
                yield f"data: [SOURCES]{raw}\n\n"
            else:
                full_answer += chunk
                yield f"data: {chunk}\n\n"
    except Exception as e:
        error_msg = f"\n\n⚠️ 生成出错: {type(e).__name__}: {str(e)}"
        full_answer += error_msg
        yield f"data: {error_msg}\n\n"

    yield "data: [DONE]\n\n"

    await conv_mgr.add_assistant_message(
        session_id, full_answer,
        metadata={"sources": sources_data, "rewritten_query": rewritten_query},
    )

    # 记录查询日志（使用独立 session，避免请求级 session 已关闭的问题）
    latency_ms = int((time.time() - start_time) * 1000)
    if QA_LOGGING_ENABLED:
        log_db = SessionLocal()
        try:
            logger = get_query_logger()
            logger.log(log_db, {
                "session_id": session_id,
                "user_id": user_id,
                "kb_id": kb_id,
                "question": question,
                "rewritten_query": rewritten_query,
                "answer": full_answer,
                "sources_json": json.dumps(sources_data, ensure_ascii=False),
                "model": generator.model_name,
                "latency_ms": latency_ms,
                "token_prompt": 0,
                "token_completion": 0,
                "token_total": 0,
                "retrieval_strategy": strategy,
                "retrieval_count": retrieval_count,
                "reranked_count": reranked_count,
            })
        finally:
            log_db.close()


# ---------------------------------------------------------------------------
# GET /api/chat/history/{session_id}
# ---------------------------------------------------------------------------

@router.get("/history/{session_id}", response_model=HistoryResponse)
async def get_chat_history(
    session_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """获取会话历史（仅自己的会话）。"""
    conv_mgr = _get_conversation_manager()
    session = await conv_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    _check_session_owner(session, user)

    messages = []
    for msg in session.messages:
        messages.append({
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp,
            "metadata": msg.metadata,
        })

    return HistoryResponse(
        session_id=session_id,
        kb_id=session.kb_id,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# DELETE /api/chat/history/{session_id}
# ---------------------------------------------------------------------------

@router.delete("/history/{session_id}")
async def delete_chat_history(
    session_id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """清空会话（仅自己的会话）。"""
    conv_mgr = _get_conversation_manager()
    session = await conv_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    _check_session_owner(session, user)

    ok = await conv_mgr.delete_session(session_id)
    return {"ok": ok}


# ---------------------------------------------------------------------------
# GET /api/chat/sessions — 列出会话
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_chat_sessions(
    kb_id: int | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """列出当前用户的会话（管理员看所有）。"""
    conv_mgr = _get_conversation_manager()
    user_id = None if user.role == "admin" else user.id
    sessions = await conv_mgr.list_sessions(kb_id, user_id=user_id)
    result = []
    for s in sessions:
        # 用第一条用户消息作为会话标题
        title = "新会话"
        for msg in s.messages:
            if msg.role == "user":
                title = msg.content[:30] + ("…" if len(msg.content) > 30 else "")
                break
        result.append({
            "session_id": s.session_id,
            "kb_id": s.kb_id,
            "user_id": s.user_id,
            "message_count": len(s.messages),
            "title": title,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })
    return result

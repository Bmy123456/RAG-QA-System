"""
数据模型：用户反馈和查询日志。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Float

from backend.models.user import Base


class Feedback(Base):
    """用户反馈"""
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)   # 提交者
    session_id = Column(String(100), nullable=False, index=True)
    message_index = Column(Integer, default=0)        # 第几轮对话
    feedback_type = Column(String(20), nullable=False) # useful / useless / correction
    question = Column(Text, default="")                # 原始问题
    answer = Column(Text, default="")                  # 原始回答
    reason = Column(Text, default="")                  # "无用"时的原因说明
    correction = Column(Text, nullable=True)           # "我要纠正"的正确答案
    status = Column(String(20), default="pending")     # pending / reviewed / adopted / dismissed / closed
    admin_reply = Column(Text, default="")             # 管理员回复
    reviewed_at = Column(DateTime, nullable=True)      # 管理员处理时间
    kb_id = Column(Integer, nullable=True, index=True) # 关联知识库
    sources_json = Column(Text, nullable=True)         # 原始引用来源 JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "message_index": self.message_index,
            "feedback_type": self.feedback_type,
            "question": self.question,
            "answer": self.answer,
            "reason": self.reason,
            "correction": self.correction,
            "status": self.status,
            "admin_reply": self.admin_reply,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "kb_id": self.kb_id,
            "sources_json": self.sources_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QueryLog(Base):
    """查询日志：记录每次问答的延迟、token 量、召回文档等。"""
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)   # 查询者
    session_id = Column(String(100), nullable=False, index=True)
    kb_id = Column(Integer, nullable=True)
    question = Column(Text, nullable=False)
    rewritten_query = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    sources_json = Column(Text, nullable=True)           # JSON: [{"chunk_id":..., "filename":...}]
    model = Column(String(100), nullable=True)
    latency_ms = Column(Integer, default=0)              # 响应延迟（毫秒）
    token_prompt = Column(Integer, default=0)
    token_completion = Column(Integer, default=0)
    token_total = Column(Integer, default=0)
    retrieval_strategy = Column(String(20), nullable=True)  # dense/sparse/hybrid
    retrieval_count = Column(Integer, default=0)         # 初始召回文档数
    reranked_count = Column(Integer, default=0)          # 重排序后文档数
    retrieval_ms = Column(Integer, default=0)            # 检索阶段耗时（毫秒）
    rerank_ms = Column(Integer, default=0)               # 重排序阶段耗时（毫秒）
    generation_ms = Column(Integer, default=0)           # LLM 生成阶段耗时（毫秒）
    retrieved_chunk_ids = Column(Text, nullable=True)    # 初始召回 chunk_id JSON 数组
    reranked_chunk_ids = Column(Text, nullable=True)     # 重排序后 chunk_id JSON 数组
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "kb_id": self.kb_id,
            "question": self.question,
            "rewritten_query": self.rewritten_query,
            "answer": self.answer,
            "sources_json": self.sources_json,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "token_prompt": self.token_prompt,
            "token_completion": self.token_completion,
            "token_total": self.token_total,
            "retrieval_strategy": self.retrieval_strategy,
            "retrieval_count": self.retrieval_count,
            "reranked_count": self.reranked_count,
            "retrieval_ms": self.retrieval_ms,
            "rerank_ms": self.rerank_ms,
            "generation_ms": self.generation_ms,
            "retrieved_chunk_ids": self.retrieved_chunk_ids,
            "reranked_chunk_ids": self.reranked_chunk_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

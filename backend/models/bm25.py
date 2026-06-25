"""
数据模型：BM25 索引持久化。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, LargeBinary, DateTime

from backend.models.user import Base


class BM25Persist(Base):
    """BM25 索引持久化（单行存储，pickle 序列化为 BLOB）。"""
    __tablename__ = "bm25_index"

    id = Column(Integer, primary_key=True, default=1)
    data = Column(LargeBinary, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

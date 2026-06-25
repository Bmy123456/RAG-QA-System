"""
数据模型：知识库和文档的 SQLAlchemy ORM 模型。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

# 使用统一的 Base，避免多表注册冲突
from backend.models.user import Base


class KnowledgeBase(Base):
    """知识库"""
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 所有者
    name = Column(String(200), nullable=False)
    description = Column(String(1000), default="")
    is_public = Column(Boolean, default=False)  # 公共知识库：所有用户可读
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("Document", back_populates="kb", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Document(Base):
    """文档"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(50), default="")
    file_size = Column(Integer, default=0)
    file_path = Column(String(1000), default="")
    status = Column(String(20), default="pending")  # pending / processing / completed / failed
    error_msg = Column(String(1000), default="")
    chunk_count = Column(Integer, default=0)
    progress = Column(Integer, default=0)  # 0-100 百分比
    progress_msg = Column(String(200), default="")  # 当前阶段描述
    created_at = Column(DateTime, default=datetime.utcnow)

    kb = relationship("KnowledgeBase", back_populates="documents")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "status": self.status,
            "error_msg": self.error_msg,
            "chunk_count": self.chunk_count,
            "progress": self.progress,
            "progress_msg": self.progress_msg,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

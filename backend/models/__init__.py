# 统一导入所有 ORM 模型，确保 Base.metadata 包含全部表定义。
from backend.models.user import Base, User
from backend.models.document import KnowledgeBase, Document
from backend.models.feedback import Feedback, QueryLog
from backend.models.bm25 import BM25Persist

__all__ = ["Base", "User", "KnowledgeBase", "Document", "Feedback", "QueryLog", "BM25Persist"]

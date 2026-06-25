"""
CRUD 操作：知识库和文档的增删改查。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.document import KnowledgeBase, Document
from backend.models.feedback import Feedback, QueryLog


# ===========================================================================
# 知识库 CRUD
# ===========================================================================

def create_kb(db: Session, name: str, description: str = "", user_id: int | None = None, is_public: bool = False) -> KnowledgeBase:
    """创建知识库"""
    kb = KnowledgeBase(name=name, description=description, user_id=user_id, is_public=is_public)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def list_kbs(db: Session, user_id: int | None = None, include_public: bool = True) -> list[KnowledgeBase]:
    """列出知识库。

    - user_id 不为 None 时：返回该用户自己的 + 公共的（如果 include_public=True）
    - user_id 为 None 时：返回全部（管理员用）
    """
    if user_id is None:
        return db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).all()

    if include_public:
        return db.query(KnowledgeBase).filter(
            (KnowledgeBase.user_id == user_id) | (KnowledgeBase.is_public == True)
        ).order_by(KnowledgeBase.created_at.desc()).all()
    else:
        return db.query(KnowledgeBase).filter(
            KnowledgeBase.user_id == user_id
        ).order_by(KnowledgeBase.created_at.desc()).all()


def get_kb(db: Session, kb_id: int) -> KnowledgeBase | None:
    """获取知识库"""
    return db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()


def update_kb(db: Session, kb_id: int, name: str | None = None, description: str | None = None) -> KnowledgeBase | None:
    """更新知识库"""
    kb = get_kb(db, kb_id)
    if not kb:
        return None
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    db.commit()
    db.refresh(kb)
    return kb


def delete_kb(db: Session, kb_id: int) -> bool:
    """删除知识库（级联删除所有文档）"""
    kb = get_kb(db, kb_id)
    if not kb:
        return False
    db.delete(kb)
    db.commit()
    return True


def count_kbs(db: Session) -> int:
    """统计知识库数量"""
    return db.query(KnowledgeBase).count()


# ===========================================================================
# 文档 CRUD
# ===========================================================================

def create_document(
    db: Session,
    kb_id: int,
    filename: str,
    file_type: str = "",
    file_size: int = 0,
    file_path: str = "",
) -> Document:
    """创建文档记录（初始状态 pending）"""
    doc = Document(
        kb_id=kb_id,
        filename=filename,
        file_type=file_type,
        file_size=file_size,
        file_path=file_path,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_documents(
    db: Session,
    kb_id: int,
    status: str | None = None,
) -> list[Document]:
    """列出知识库下的文档"""
    q = db.query(Document).filter(Document.kb_id == kb_id)
    if status:
        q = q.filter(Document.status == status)
    return q.order_by(Document.created_at.desc()).all()


def get_document(db: Session, doc_id: int) -> Document | None:
    """获取文档"""
    return db.query(Document).filter(Document.id == doc_id).first()


def update_document_status(
    db: Session,
    doc_id: int,
    status: str,
    error_msg: str | None = None,
    chunk_count: int | None = None,
    progress: int | None = None,
    progress_msg: str | None = None,
) -> Document | None:
    """更新文档状态和进度"""
    doc = get_document(db, doc_id)
    if not doc:
        return None
    doc.status = status
    if error_msg is not None:
        doc.error_msg = error_msg
    if chunk_count is not None:
        doc.chunk_count = chunk_count
    if progress is not None:
        doc.progress = progress
    if progress_msg is not None:
        doc.progress_msg = progress_msg
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, doc_id: int) -> bool:
    """删除文档"""
    doc = get_document(db, doc_id)
    if not doc:
        return False
    db.delete(doc)
    db.commit()
    return True


def count_documents(db: Session, kb_id: int | None = None, status: str | None = None) -> int:
    """统计文档数量"""
    q = db.query(Document)
    if kb_id is not None:
        q = q.filter(Document.kb_id == kb_id)
    if status:
        q = q.filter(Document.status == status)
    return q.count()


def get_all_documents(db: Session, status: str | None = None) -> list[Document]:
    """列出所有文档"""
    q = db.query(Document)
    if status:
        q = q.filter(Document.status == status)
    return q.order_by(Document.created_at.desc()).all()


# ===========================================================================
# 反馈 CRUD
# ===========================================================================

def create_feedback(
    db: Session,
    session_id: str,
    feedback_type: str,
    message_index: int = 0,
    question: str = "",
    answer: str = "",
    reason: str = "",
    correction: str | None = None,
    user_id: int | None = None,
    kb_id: int | None = None,
    sources_json: str | None = None,
) -> Feedback:
    """创建反馈"""
    fb = Feedback(
        user_id=user_id,
        session_id=session_id,
        message_index=message_index,
        feedback_type=feedback_type,
        question=question,
        answer=answer,
        reason=reason,
        correction=correction,
        kb_id=kb_id,
        sources_json=sources_json,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def get_feedback(db: Session, feedback_id: int) -> Feedback | None:
    """获取单条反馈"""
    return db.query(Feedback).filter(Feedback.id == feedback_id).first()


def list_feedbacks(
    db: Session,
    session_id: str | None = None,
    feedback_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: int | None = None,
    kb_id: int | None = None,
    created_after: str | None = None,
) -> tuple[list[Feedback], int]:
    """列出反馈，返回 (列表, 总数)"""
    q = db.query(Feedback)
    if session_id:
        q = q.filter(Feedback.session_id == session_id)
    if feedback_type:
        q = q.filter(Feedback.feedback_type == feedback_type)
    if status:
        q = q.filter(Feedback.status == status)
    if user_id is not None:
        q = q.filter(Feedback.user_id == user_id)
    if kb_id is not None:
        q = q.filter(Feedback.kb_id == kb_id)
    if created_after:
        from datetime import datetime as _dt
        try:
            dt = _dt.fromisoformat(created_after)
            q = q.filter(Feedback.created_at >= dt)
        except ValueError:
            pass
    total = q.count()
    items = q.order_by(Feedback.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def update_feedback_status(
    db: Session,
    feedback_id: int,
    status: str,
    admin_reply: str = "",
) -> Feedback | None:
    """管理员更新反馈状态"""
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        return None
    fb.status = status
    if admin_reply:
        fb.admin_reply = admin_reply
    if status in ("reviewed", "adopted", "dismissed"):
        from datetime import datetime
        fb.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(fb)
    return fb


def get_feedback_stats(db: Session, user_id: int | None = None) -> dict:
    """反馈统计"""
    from sqlalchemy import func

    q = db.query(Feedback)
    if user_id is not None:
        q = q.filter(Feedback.user_id == user_id)
    total = q.count()
    useful = q.filter(Feedback.feedback_type == "useful").count()
    useless = q.filter(Feedback.feedback_type == "useless").count()
    corrections = q.filter(Feedback.feedback_type == "correction").count()
    return {
        "total": total,
        "useful": useful,
        "useless": useless,
        "corrections": corrections,
        "satisfaction_rate": useful / max(1, useful + useless),
    }


def get_feedback_trend(db: Session, days: int = 7) -> list[dict]:
    """近 N 天每日反馈数趋势"""
    from sqlalchemy import func
    from datetime import timedelta

    start = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(
            func.date(Feedback.created_at).label("date"),
            func.count().label("count"),
        )
        .filter(Feedback.created_at >= start)
        .group_by(func.date(Feedback.created_at))
        .order_by(func.date(Feedback.created_at))
        .all()
    )
    # 补全无数据的日期
    result = []
    from datetime import datetime as _dt
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        count = next((r.count for r in rows if str(r.date) == d), 0)
        result.append({"date": d, "count": count})
    return result


def get_feedback_distribution(db: Session) -> dict:
    """反馈类型分布"""
    from sqlalchemy import func

    rows = (
        db.query(Feedback.feedback_type, func.count().label("count"))
        .group_by(Feedback.feedback_type)
        .all()
    )
    return {r.feedback_type: r.count for r in rows}


def get_pending_feedback_count(db: Session) -> int:
    """待处理反馈数"""
    return db.query(Feedback).filter(Feedback.status == "pending").count()


def get_feedback_export(db: Session, **filters) -> list[dict]:
    """导出反馈数据（返回字典列表）"""
    q = db.query(Feedback)
    if filters.get("feedback_type"):
        q = q.filter(Feedback.feedback_type == filters["feedback_type"])
    if filters.get("status"):
        q = q.filter(Feedback.status == filters["status"])
    if filters.get("kb_id"):
        q = q.filter(Feedback.kb_id == filters["kb_id"])
    if filters.get("created_after"):
        try:
            dt = datetime.fromisoformat(filters["created_after"])
            q = q.filter(Feedback.created_at >= dt)
        except ValueError:
            pass
    items = q.order_by(Feedback.created_at.desc()).all()
    return [f.to_dict() for f in items]


# ===========================================================================
# 查询日志 CRUD
# ===========================================================================

def create_query_log(db: Session, **kwargs) -> QueryLog:
    """创建查询日志"""
    log = QueryLog(**kwargs)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def list_query_logs(
    db: Session,
    session_id: str | None = None,
    kb_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    user_id: int | None = None,
) -> list[QueryLog]:
    """列出查询日志"""
    q = db.query(QueryLog)
    if session_id:
        q = q.filter(QueryLog.session_id == session_id)
    if kb_id is not None:
        q = q.filter(QueryLog.kb_id == kb_id)
    if user_id is not None:
        q = q.filter(QueryLog.user_id == user_id)
    return q.order_by(QueryLog.created_at.desc()).offset(offset).limit(limit).all()


def get_query_log_stats(db: Session) -> dict:
    """查询日志统计"""
    from sqlalchemy import func

    total = db.query(QueryLog).count()
    avg_latency = db.query(func.avg(QueryLog.latency_ms)).scalar() or 0
    avg_tokens = db.query(func.avg(QueryLog.token_total)).scalar() or 0
    avg_retrieval = db.query(func.avg(QueryLog.retrieval_count)).scalar() or 0

    return {
        "total": total,
        "avg_latency_ms": round(avg_latency, 1),
        "avg_tokens": round(avg_tokens, 1),
        "avg_retrieval_count": round(avg_retrieval, 1),
    }

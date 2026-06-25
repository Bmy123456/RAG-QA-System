"""
评估与反馈 API：用户反馈提交、查询日志、离线评估。

日志记录每次问答的延迟、token 量、召回文档 id，用于后续分析。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.crud import (
    create_feedback, get_feedback, list_feedbacks, get_feedback_stats,
    update_feedback_status, get_feedback_trend, get_feedback_distribution,
    get_pending_feedback_count, get_feedback_export,
    create_query_log, list_query_logs, get_query_log_stats,
    get_recall_evaluation_data,
)
from backend.db.session import get_db
from backend.api.auth import require_user, require_admin
from backend.models.user import User

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int = 0
    feedback_type: str          # useful / useless / correction
    reason: str | None = None   # "无用"时的原因
    correction: str | None = None  # "我要纠正"的正确答案
    question: str | None = None # 原始问题
    answer: str | None = None   # 原始回答
    kb_id: int | None = None    # 关联知识库
    sources_json: str | None = None  # 引用来源 JSON


# ---------------------------------------------------------------------------
# 反馈 API
# ---------------------------------------------------------------------------

@router.post("/feedback")
def submit_feedback(
    data: FeedbackRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """提交用户反馈。"""
    if data.feedback_type not in ("useful", "useless", "correction"):
        raise HTTPException(status_code=400, detail="无效的反馈类型，须为 useful/useless/correction")

    if data.feedback_type == "useless" and not data.reason:
        raise HTTPException(status_code=400, detail="标记'无用'时请填写原因")

    if data.feedback_type == "correction" and not data.correction:
        raise HTTPException(status_code=400, detail="提交纠正时请填写正确答案")

    fb = create_feedback(
        db,
        session_id=data.session_id,
        feedback_type=data.feedback_type,
        message_index=data.message_index,
        question=data.question or "",
        answer=data.answer or "",
        reason=data.reason or "",
        correction=data.correction,
        user_id=user.id,
        kb_id=data.kb_id,
        sources_json=data.sources_json,
    )
    return fb.to_dict()


@router.get("/feedback")
def get_feedbacks(
    session_id: str | None = None,
    feedback_type: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """获取反馈列表（普通用户只看自己的，管理员看所有）。"""
    uid = None if user.role == "admin" else user.id
    items, total = list_feedbacks(
        db, session_id, feedback_type, status, limit, offset, user_id=uid,
    )
    return {"items": [f.to_dict() for f in items], "total": total}


@router.get("/feedback/{feedback_id}")
def get_feedback_detail(
    feedback_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """获取单条反馈详情（只能看自己的，管理员可看所有）。"""
    fb = get_feedback(db, feedback_id)
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if user.role != "admin" and fb.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看此反馈")
    return fb.to_dict()


@router.get("/feedback/stats")
def feedback_stats(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """反馈统计概览（管理员看全局，普通用户看自己的）。"""
    uid = None if user.role == "admin" else user.id
    return get_feedback_stats(db, user_id=uid)


# ---------------------------------------------------------------------------
# 查询日志 API
# ---------------------------------------------------------------------------

@router.get("/logs")
def get_query_logs(
    session_id: str | None = None,
    kb_id: int | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """查询日志列表（普通用户只看自己的，管理员看所有）。"""
    uid = None if user.role == "admin" else user.id
    logs = list_query_logs(db, session_id, kb_id, limit, offset, user_id=uid)
    return [l.to_dict() for l in logs]


@router.get("/logs/stats")
def query_log_stats(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """查询日志统计。"""
    return get_query_log_stats(db)


# ---------------------------------------------------------------------------
# 离线评估 API
# ---------------------------------------------------------------------------

@router.get("/retrieval")
def run_retrieval_evaluation(db: Session = Depends(get_db)):
    """触发离线检索评估。

    需要有标注数据集 data/evaluation/retrieval_test.json。
    格式: [{"query": "...", "relevant_doc_ids": ["id1", "id2"], "kb_id": 1}]
    """
    from backend.config.settings import EVAL_DIR
    test_path = EVAL_DIR / "retrieval_test.json"

    with open(test_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)

    if not test_data:
        raise HTTPException(status_code=400, detail="评估数据集为空，请先添加测试数据")

    from backend.evaluation.evaluate_retrieval import evaluate_retrieval
    results = evaluate_retrieval(test_data, db)
    return results


@router.get("/recall-data")
def get_recall_data(
    kb_id: int | None = None,
    limit: int = Query(500, ge=1, le=5000),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """导出召回评估数据（管理员）。

    返回每次查询的初始召回 chunk_id 列表和重排序后 chunk_id 列表，
    可配合标注的 relevant_doc_ids 离线计算 Recall@K、Precision@K 等指标。
    """
    return get_recall_evaluation_data(db, kb_id=kb_id, limit=limit)


@router.get("/generation")
def run_generation_evaluation(db: Session = Depends(get_db)):
    """触发离线生成评估。

    需要有标注数据集 data/evaluation/generation_test.json。
    格式: [{"question": "...", "context": "...", "answer": "...", "reference": "..."}]
    """
    from backend.config.settings import EVAL_DIR
    test_path = EVAL_DIR / "generation_test.json"

    with open(test_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)

    if not test_data:
        raise HTTPException(status_code=400, detail="评估数据集为空，请先添加测试数据")

    from backend.evaluation.evaluate_generation import evaluate_generation
    results = evaluate_generation(test_data)
    return results


@router.get("/stats")
def evaluation_stats(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """综合统计：反馈 + 查询日志。"""
    uid = None if user.role == "admin" else user.id
    return {
        "feedback": get_feedback_stats(db, user_id=uid),
        "query_log": get_query_log_stats(db),
    }


@router.put("/feedback/{feedback_id}/status")
def update_feedback_status_api(
    feedback_id: int,
    status: str = Query(...),
    admin_reply: str = Query(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """更新反馈状态（用户可关闭自己的反馈，管理员可审阅/采纳）。"""
    fb = get_feedback(db, feedback_id)
    if not fb:
        raise HTTPException(status_code=404, detail="反馈不存在")
    # 普通用户只能关闭自己的反馈
    if user.role != "admin":
        if fb.user_id != user.id:
            raise HTTPException(status_code=403, detail="无权操作此反馈")
        if status not in ("closed",):
            raise HTTPException(status_code=403, detail="普通用户只能关闭反馈")
    updated = update_feedback_status(db, feedback_id, status, admin_reply)
    return updated.to_dict()


# ---------------------------------------------------------------------------
# 管理员 API
# ---------------------------------------------------------------------------

@router.get("/admin/stats")
def admin_feedback_stats(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员综合统计：反馈统计 + 趋势 + 分布 + 待处理数。"""
    stats = get_feedback_stats(db)
    stats["trend"] = get_feedback_trend(db, days=7)
    stats["distribution"] = get_feedback_distribution(db)
    stats["pending_count"] = get_pending_feedback_count(db)
    return stats


@router.get("/admin/export")
def admin_export_feedback(
    format: str = Query("csv"),
    feedback_type: str | None = None,
    status: str | None = None,
    kb_id: int | None = None,
    created_after: str | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """导出反馈数据（CSV 或 JSON）。"""
    data = get_feedback_export(
        db, feedback_type=feedback_type, status=status,
        kb_id=kb_id, created_after=created_after,
    )
    if format == "json":
        return data

    # CSV 输出
    import csv
    import io
    from fastapi.responses import StreamingResponse

    if not data:
        return StreamingResponse(
            iter(["暂无数据"]),
            media_type="text/plain",
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=feedback_export.csv"},
    )


# ---------------------------------------------------------------------------
# QueryLogger — 集成到 chat.py 中使用
# ---------------------------------------------------------------------------

class QueryLogger:
    """查询日志记录器：同时写 SQLite 和 JSON Lines 文件。"""

    def __init__(self, log_file: str | None = None):
        self._log_file = log_file
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    def log(self, db: Session, data: dict) -> None:
        """记录查询日志。

        参数:
            db:   数据库会话
            data: 日志数据字典
        """
        # 写 SQLite
        create_query_log(db, **data)

        # 写 JSON Lines 文件
        if self._log_file:
            data["timestamp"] = datetime.utcnow().isoformat()
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")


# 全局实例
_query_logger: QueryLogger | None = None


def get_query_logger() -> QueryLogger:
    global _query_logger
    if _query_logger is None:
        from backend.config.settings import DATA_DIR
        _query_logger = QueryLogger(log_file=str(DATA_DIR / "query_logs.jsonl"))
    return _query_logger

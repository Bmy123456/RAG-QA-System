"""
仪表盘 API：系统监控指标端点，仅管理员可访问。

提供服务质量概览、延迟分解、错误率、反馈趋势、Token 消耗、告警等数据。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.auth import require_admin
from backend.db.session import get_db
from backend.db.crud import (
    get_dashboard_overview,
    get_latency_breakdown,
    get_hourly_feedback_trend,
    get_top_disliked_docs,
    get_token_usage_by_model,
    get_dashboard_alerts,
)
from backend.middleware.metrics import metrics_store

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """服务质量概览：今日问答量、P95 延迟、满意度。"""
    return get_dashboard_overview(db)


@router.get("/latency-breakdown")
def latency_breakdown(
    hours: int = Query(24, ge=1, le=168),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """核心链路延迟分解：检索/重排序/生成各阶段 avg 和 P95。"""
    return get_latency_breakdown(db, hours)


@router.get("/error-rate")
def error_rate(
    hours: int = Query(24, ge=1, le=72),
    user=Depends(require_admin),
):
    """HTTP 错误率时间序列（按小时）。"""
    return metrics_store.get_hourly_timeseries(hours)


@router.get("/feedback-trend")
def feedback_trend(
    hours: int = Query(24, ge=1, le=168),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """用户反馈趋势（按小时的点赞/点踩）。"""
    return get_hourly_feedback_trend(db, hours)


@router.get("/feedback-top-docs")
def feedback_top_docs(
    limit: int = Query(5, ge=1, le=20),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """高频点踩文档 Top N。"""
    return get_top_disliked_docs(db, limit)


@router.get("/token-usage")
def token_usage(
    hours: int = Query(24, ge=1, le=168),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Token 消耗统计（按模型，日累计）。"""
    return get_token_usage_by_model(db, hours)


@router.get("/alerts")
def alerts(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """当前告警列表。"""
    return get_dashboard_alerts(db)


@router.get("/http-overview")
def http_overview(
    hours: int = Query(24, ge=1, le=72),
    user=Depends(require_admin),
):
    """HTTP 请求级概览（QPS、错误率、延迟百分位）。"""
    import time
    since = time.time() - hours * 3600
    return metrics_store.get_overview(since)

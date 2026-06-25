"""
HTTP 请求级指标中间件。

在内存中维护滚动窗口（最近 24 小时），记录：
- 每个请求的耗时、状态码
- 按分钟聚合的 QPS、错误率、延迟百分位
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass
class RequestMetric:
    """单次请求指标。"""
    timestamp: float
    method: str
    path: str
    status_code: int
    latency_ms: float


@dataclass
class MetricsStore:
    """全局指标存储（进程内，滚动窗口）。"""
    requests: deque = field(default_factory=lambda: deque(maxlen=100_000))

    def add(self, metric: RequestMetric):
        self.requests.append(metric)

    def _clean(self, max_age_seconds: float = 86400):
        """清理超过 max_age 的旧数据。"""
        cutoff = time.time() - max_age_seconds
        while self.requests and self.requests[0].timestamp < cutoff:
            self.requests.popleft()

    def get_overview(self, since: float | None = None) -> dict:
        """获取概览指标。"""
        self._clean()
        if since is None:
            since = time.time() - 86400  # 默认最近 24 小时

        relevant = [r for r in self.requests if r.timestamp >= since]
        if not relevant:
            return {
                "total_requests": 0,
                "error_5xx_count": 0,
                "error_5xx_rate": 0.0,
                "avg_latency_ms": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "p99_latency_ms": 0,
                "qps": 0.0,
            }

        latencies = sorted(r.latency_ms for r in relevant)
        errors_5xx = sum(1 for r in relevant if r.status_code >= 500)
        duration = max(relevant[-1].timestamp - relevant[0].timestamp, 1)

        return {
            "total_requests": len(relevant),
            "error_5xx_count": errors_5xx,
            "error_5xx_rate": round(errors_5xx / len(relevant), 4),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
            "p50_latency_ms": round(_percentile(latencies, 50), 1),
            "p95_latency_ms": round(_percentile(latencies, 95), 1),
            "p99_latency_ms": round(_percentile(latencies, 99), 1),
            "qps": round(len(relevant) / duration, 2),
        }

    def get_hourly_timeseries(self, hours: int = 24) -> list[dict]:
        """按小时聚合的时间序列。"""
        self._clean()
        now = time.time()
        result = []

        for h in range(hours, 0, -1):
            start = now - h * 3600
            end = start + 3600
            bucket = [r for r in self.requests if start <= r.timestamp < end]

            if bucket:
                latencies = sorted(r.latency_ms for r in bucket)
                errors = sum(1 for r in bucket if r.status_code >= 500)
                result.append({
                    "hour": time.strftime("%Y-%m-%d %H:00", time.localtime(start)),
                    "count": len(bucket),
                    "error_count": errors,
                    "error_rate": round(errors / len(bucket), 4),
                    "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
                    "p95_latency_ms": round(_percentile(latencies, 95), 1),
                })
            else:
                result.append({
                    "hour": time.strftime("%Y-%m-%d %H:00", time.localtime(start)),
                    "count": 0,
                    "error_count": 0,
                    "error_rate": 0.0,
                    "avg_latency_ms": 0,
                    "p95_latency_ms": 0,
                })

        return result


def _percentile(sorted_data: list[float], p: int) -> float:
    """计算百分位数（输入必须已排序）。"""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# 全局单例
metrics_store = MetricsStore()


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的耗时和状态码。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        try:
            response = await call_next(request)
        except Exception:
            # 未捕获异常也算 5xx
            latency_ms = (time.time() - start) * 1000
            metrics_store.add(RequestMetric(
                timestamp=start,
                method=request.method,
                path=str(request.url.path),
                status_code=500,
                latency_ms=latency_ms,
            ))
            raise

        latency_ms = (time.time() - start) * 1000
        metrics_store.add(RequestMetric(
            timestamp=start,
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            latency_ms=latency_ms,
        ))
        return response

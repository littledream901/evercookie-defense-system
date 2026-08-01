"""Prometheus 指标定义与注册中心。

集中定义业务指标，避免各服务重复声明；同时提供 /metrics 端点辅助函数。
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.registry import REGISTRY as _DEFAULT_REGISTRY

_registry: CollectorRegistry = _DEFAULT_REGISTRY


def get_registry() -> CollectorRegistry:
    return _registry


http_requests_total = Counter(
    "fangyu_http_requests_total",
    "HTTP 请求总数",
    ["service", "method", "path", "status"],
    registry=_registry,
)

http_request_duration_seconds = Histogram(
    "fangyu_http_request_duration_seconds",
    "HTTP 请求耗时",
    ["service", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_registry,
)

decision_requests_total = Counter(
    "fangyu_decision_requests_total",
    "决策请求数",
    # 标签名随处置模型改为 verdict：三层模型里 action 已被 verdict/mechanism 取代。
    ["app_id", "verdict"],
    registry=_registry,
)

decision_latency_seconds = Histogram(
    "fangyu_decision_latency_seconds",
    "决策耗时",
    ["app_id", "stage"],
    buckets=(0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
    registry=_registry,
)

decision_cache_hits_total = Counter(
    "fangyu_decision_cache_hits_total",
    "决策缓存命中数",
    ["app_id", "layer"],
    registry=_registry,
)

stream_events_consumed_total = Counter(
    "fangyu_stream_events_consumed_total",
    "Stream 消费事件总数",
    ["stream", "consumer_group"],
    registry=_registry,
)

stream_events_processed_total = Counter(
    "fangyu_stream_events_processed_total",
    "Stream 处理成功事件数",
    ["stream", "consumer_group", "status"],
    registry=_registry,
)

stream_dead_letter_total = Counter(
    "fangyu_stream_dead_letter_total",
    "Stream 死信数量",
    ["stream", "reason"],
    registry=_registry,
)

stream_lag = Gauge(
    "fangyu_stream_lag",
    "Stream 消费滞后",
    ["stream", "consumer_group"],
    registry=_registry,
)

admin_login_failure_total = Counter(
    "fangyu_admin_login_failure_total",
    "admin-api 登录失败总数",
    ["service", "reason"],
    registry=_registry,
)


def metrics_endpoint() -> tuple[bytes, str]:
    """返回 (payload, content_type)，供各服务的 /metrics 路由复用。"""
    return generate_latest(_registry), "text/plain; version=0.0.4; charset=utf-8"

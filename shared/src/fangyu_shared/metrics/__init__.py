"""Prometheus 指标包。"""

from __future__ import annotations

from fangyu_shared.metrics.decorators import track_errors, track_latency
from fangyu_shared.metrics.middleware import PrometheusMiddleware
from fangyu_shared.metrics.registry import (
    decision_cache_hits_total,
    decision_latency_seconds,
    decision_requests_total,
    get_registry,
    http_request_duration_seconds,
    http_requests_total,
    metrics_endpoint,
    stream_dead_letter_total,
    stream_events_consumed_total,
    stream_events_processed_total,
    stream_lag,
)

__all__ = [
    "PrometheusMiddleware",
    "decision_cache_hits_total",
    "decision_latency_seconds",
    "decision_requests_total",
    "get_registry",
    "http_request_duration_seconds",
    "http_requests_total",
    "metrics_endpoint",
    "stream_dead_letter_total",
    "stream_events_consumed_total",
    "stream_events_processed_total",
    "stream_lag",
    "track_errors",
    "track_latency",
]

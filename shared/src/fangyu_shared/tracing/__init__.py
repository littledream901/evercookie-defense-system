"""OpenTelemetry Tracing 初始化与工具集。"""

from .propagation import (
    extract_context,
    get_span_id,
    get_trace_id,
    get_traceparent,
    inject_traceparent,
)
from .setup import get_tracer, setup_tracing
from .structlog_processor import otel_trace_processor

__all__ = [
    "setup_tracing",
    "get_tracer",
    "inject_traceparent",
    "extract_context",
    "get_traceparent",
    "get_trace_id",
    "get_span_id",
    "otel_trace_processor",
]

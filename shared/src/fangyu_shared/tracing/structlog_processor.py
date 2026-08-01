"""structlog processor：把当前 OTel span 的 trace_id/span_id 注入日志字段。"""

from __future__ import annotations

from typing import Any

import structlog
from opentelemetry import trace


def otel_trace_processor(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor，自动为每条日志附加当前的 trace_id 和 span_id。"""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

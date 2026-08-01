"""W3C TraceContext 与 B3 传播器工具。

用于跨进程边界（HTTP → Redis Stream → Worker）传递 trace 上下文。
"""

from __future__ import annotations

from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_propagator = TraceContextTextMapPropagator()


def inject_traceparent(carrier: dict[str, Any]) -> None:
    """把当前 span 的 traceparent 注入到 carrier dict 中。"""
    propagate.inject(carrier)


def extract_context(carrier: dict[str, Any]) -> Context:
    """从 carrier dict 中提取 OTel Context（含 span 信息）。"""
    return propagate.extract(carrier)


def get_traceparent() -> str | None:
    """获取当前 span 的 W3C traceparent 字符串，无活动 span 时返回 None。"""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None
    trace_id = format(ctx.trace_id, "032x")
    span_id = format(ctx.span_id, "016x")
    flags = "01" if ctx.trace_flags else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def get_trace_id() -> str | None:
    """获取当前 trace_id（hex 字符串），无活动 span 时返回 None。"""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


def get_span_id() -> str | None:
    """获取当前 span_id（hex 字符串），无活动 span 时返回 None。"""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.span_id, "016x")

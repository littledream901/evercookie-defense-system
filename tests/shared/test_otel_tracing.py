"""OTel Tracing 单元测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def _stream_message_cls():
    path = Path(__file__).resolve().parents[2] / "worker" / "src" / "domain" / "event" / "stream_message.py"
    spec = importlib.util.spec_from_file_location("worker_stream_message", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.StreamMessage


def _make_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_setup_tracing_returns_provider():
    from fangyu_shared.tracing.setup import setup_tracing

    provider = setup_tracing(service_name="test-svc", otlp_endpoint=None)
    assert isinstance(provider, TracerProvider)
    resource = provider.resource
    assert resource.attributes.get("service.name") == "test-svc"


def test_get_traceparent_with_active_span():
    from fangyu_shared.tracing.propagation import get_traceparent, get_trace_id, get_span_id

    provider, _ = _make_provider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("test-span"):
        tp = get_traceparent()
        tid = get_trace_id()
        sid = get_span_id()

    assert tp is not None
    assert tp.startswith("00-")
    parts = tp.split("-")
    assert len(parts) == 4
    assert len(parts[1]) == 32
    assert len(parts[2]) == 16
    assert tid is not None and len(tid) == 32
    assert sid is not None and len(sid) == 16


def test_get_traceparent_without_span():
    from fangyu_shared.tracing.propagation import get_traceparent

    trace.set_tracer_provider(TracerProvider())
    result = get_traceparent()
    assert result is None


def test_inject_and_extract_traceparent():
    from fangyu_shared.tracing.propagation import inject_traceparent, extract_context

    provider, _ = _make_provider()
    trace.set_tracer_provider(provider)
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("parent-span") as span:
        carrier: dict = {}
        inject_traceparent(carrier)
        assert "traceparent" in carrier

    ctx = extract_context(carrier)
    assert ctx is not None


def test_otel_trace_processor_injects_ids():
    from fangyu_shared.tracing.structlog_processor import otel_trace_processor

    provider, _ = _make_provider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("log-span"):
        event_dict: dict = {"event": "test_log"}
        result = otel_trace_processor(None, "info", event_dict)

    assert "trace_id" in result
    assert "span_id" in result
    assert len(result["trace_id"]) == 32
    assert len(result["span_id"]) == 16


def test_otel_trace_processor_no_span():
    from fangyu_shared.tracing.structlog_processor import otel_trace_processor

    trace.set_tracer_provider(TracerProvider())
    event_dict: dict = {"event": "test_log"}
    result = otel_trace_processor(None, "info", event_dict)
    assert "trace_id" not in result
    assert "span_id" not in result


def test_stream_publisher_injects_traceparent():
    from fangyu_shared.tracing.propagation import get_traceparent

    provider, _ = _make_provider()
    trace.set_tracer_provider(provider)
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("gateway-decision"):
        tp = get_traceparent()

    assert tp is not None
    assert tp.startswith("00-")


def test_stream_message_carries_traceparent():
    StreamMessage = _stream_message_cls()

    msg = StreamMessage(
        stream="fangyu:events:v2",
        message_id="1-1",
        payload={"foo": "bar"},
        traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01",
    )
    assert msg.traceparent is not None
    assert msg.traceparent.startswith("00-")


def test_stream_message_without_traceparent():
    StreamMessage = _stream_message_cls()

    msg = StreamMessage(
        stream="fangyu:events:v2",
        message_id="1-2",
        payload={"foo": "bar"},
    )
    assert msg.traceparent is None

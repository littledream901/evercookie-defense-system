"""OTel Tracer 初始化：setup_tracing() 在各服务 lifespan 中调用一次。"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, TraceIdRatioBased


def setup_tracing(
    *,
    service_name: str,
    service_version: str = "2.0.0",
    otlp_endpoint: str | None = None,
    sample_rate: float = 1.0,
    console_export: bool = False,
) -> TracerProvider:
    """初始化 TracerProvider 并注册为全局。

    Args:
        service_name:    服务名称，写入 Resource 中。
        service_version: 版本号，写入 Resource 中。
        otlp_endpoint:   OTLP gRPC endpoint，如 "http://jaeger:4317"。
                         为 None 时不导出（NoOp / 仅 console）。
        sample_rate:     采样率 0.0~1.0。生产建议 0.1~0.2。
        console_export:  是否同时输出到控制台（调试用）。
    """
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )

    if sample_rate <= 0:
        sampler = ALWAYS_OFF
    elif sample_rate >= 1.0:
        sampler = ALWAYS_ON
    else:
        sampler = TraceIdRatioBased(sample_rate)

    provider = TracerProvider(resource=resource, sampler=sampler)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return provider


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def noop_span() -> trace.NonRecordingSpan:
    return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)

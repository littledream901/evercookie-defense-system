"""structlog 配置入口。"""

from __future__ import annotations

import logging
import sys
from typing import Any, Literal

import structlog

LogFormat = Literal["json", "console"]


def configure_logging(
    *,
    level: str = "INFO",
    fmt: LogFormat = "json",
    service_name: str | None = None,
    enable_otel: bool = True,
) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if service_name:
        shared_processors.insert(
            0,
            lambda _logger, _name, event_dict: {**event_dict, "service": service_name},
        )

    if enable_otel:
        try:
            from fangyu_shared.tracing.structlog_processor import otel_trace_processor
            shared_processors.insert(0, otel_trace_processor)
        except ImportError:
            pass

    if fmt == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "aiohttp.access"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)

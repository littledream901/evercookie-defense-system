"""请求级上下文变量。

使用 contextvars 保证在 asyncio 协程中不会串数据。
所有键值都会通过 structlog 的 merge_contextvars 处理器自动附加到日志。
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

import structlog

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_app_id_var: ContextVar[str | None] = ContextVar("app_id", default=None)


def bind_request_context(
    *,
    request_id: str | None = None,
    app_id: str | int | None = None,
    **extra: Any,
) -> str:
    """在当前上下文绑定请求元数据，返回最终使用的 request_id。"""
    rid = request_id or uuid.uuid4().hex
    _request_id_var.set(rid)
    if app_id is not None:
        _app_id_var.set(str(app_id))
    structlog.contextvars.bind_contextvars(request_id=rid, app_id=app_id, **extra)
    return rid


def clear_request_context() -> None:
    _request_id_var.set(None)
    _app_id_var.set(None)
    structlog.contextvars.clear_contextvars()


def get_request_id() -> str | None:
    return _request_id_var.get()


def get_app_id() -> str | None:
    return _app_id_var.get()

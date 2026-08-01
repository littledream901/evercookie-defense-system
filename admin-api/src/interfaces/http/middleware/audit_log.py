"""审计日志中间件。

拦截所有 mutating（POST/PUT/PATCH/DELETE）请求，异步写入 sys_audit_log。

设计要点：
- 只审计 mutating 方法；GET / HEAD / OPTIONS 全部跳过
- 白名单路径（healthz / metrics / login refresh 等）跳过
- 4xx / 5xx 也记录（合规要求：失败尝试同样有价值）
- 落库放到 response 发出之后的独立协程，尽量不影响主链路延迟
- 无当前用户时 user_id 记为 NULL；path/method/ip/UA 仍保留
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from fangyu_shared.logging import get_logger

from src.domain.audit.entities import AuditAction

_logger = get_logger("admin.audit_middleware")

_METHOD_ACTION = {
    "POST": AuditAction.CREATE.value,
    "PUT": AuditAction.UPDATE.value,
    "PATCH": AuditAction.UPDATE.value,
    "DELETE": AuditAction.DELETE.value,
}

# 路径 → resource 提取：匹配 /v2/{resource}[/rest]，rest 中第一段若为纯数字/uuid 视为 resource_id。
_RESOURCE_PATH_RE = re.compile(r"^/v2/([a-zA-Z_\-]+)(?:/([^/?]+))?")

# 特殊子路径 → 更细粒度的 action
_SUBPATH_ACTION_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/login$"), AuditAction.LOGIN.value),
    (re.compile(r"/logout$"), AuditAction.LOGOUT.value),
    (re.compile(r"/rotate.*key$", re.IGNORECASE), AuditAction.ROTATE.value),
    (re.compile(r"/publish$"), AuditAction.PUBLISH.value),
    (re.compile(r"/disable$"), AuditAction.DISABLE.value),
)


class AuditLogMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        *,
        recorder: Callable[[dict[str, Any]], Awaitable[None]],
        methods: tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE"),
        skip_patterns: tuple[str, ...] = (
            r"^/v2/health",
            r"^/healthz",
            r"^/readyz",
            r"^/metrics",
            r"^/v2/auth/refresh$",
        ),
    ) -> None:
        super().__init__(app)
        self._recorder = recorder
        self._methods = set(methods)
        self._skip_patterns = [re.compile(p) for p in skip_patterns]

    def _should_skip(self, method: str, path: str) -> bool:
        if method not in self._methods:
            return True
        return any(p.search(path) for p in self._skip_patterns)

    async def dispatch(  # type: ignore[override]
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method.upper()
        path = request.url.path
        if self._should_skip(method, path):
            return await call_next(request)

        response = await call_next(request)

        try:
            resource, resource_id = _extract_resource(path)
            action = _infer_action(method, path)
            user_id = getattr(request.state, "current_user_id", None)
            username = getattr(request.state, "current_username", "") or ""
            request_id = (
                getattr(request.state, "request_id", None)
                or request.headers.get("x-request-id")
                or ""
            )
            payload: dict[str, Any] = {
                "user_id": user_id,
                "username": username,
                "method": method,
                "path": path,
                "resource": resource,
                "resource_id": resource_id,
                "action": action,
                "status_code": response.status_code,
                "ip": _client_ip(request),
                "user_agent": (request.headers.get("user-agent") or "")[:512],
                "request_id": request_id,
                "detail": None,
            }
        except Exception as exc:  # pragma: no cover - 提取失败不影响主流程
            _logger.warning("audit_extract_failed", error=str(exc), path=path)
            return response

        # fire-and-forget：确保不阻塞响应
        task = asyncio.create_task(_safe_record(self._recorder, payload))
        # 附加到 request.state 便于测试等待
        request.state.audit_task = task
        return response


async def _safe_record(
    recorder: Callable[[dict[str, Any]], Awaitable[None]],
    payload: dict[str, Any],
) -> None:
    try:
        await recorder(payload)
    except Exception as exc:  # pragma: no cover
        _logger.error("audit_record_failed", error=str(exc), path=payload.get("path"))


def _extract_resource(path: str) -> tuple[str, str]:
    m = _RESOURCE_PATH_RE.match(path)
    if not m:
        return "", ""
    resource = m.group(1) or ""
    tail = m.group(2) or ""
    # 只有当 tail 明显是 id（数字 / uuid 风格）才当 resource_id，否则视为子操作路径
    if tail and (tail.isdigit() or re.fullmatch(r"[0-9a-fA-F\-]{8,}", tail)):
        return resource, tail
    return resource, ""


def _infer_action(method: str, path: str) -> str:
    for pattern, action in _SUBPATH_ACTION_HINTS:
        if pattern.search(path):
            return action
    return _METHOD_ACTION.get(method, AuditAction.OTHER.value)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client:
        return request.client.host
    return ""

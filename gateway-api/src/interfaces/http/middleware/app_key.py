"""App Key 校验与解析。

Gateway 通过 HTTP header 中的 API Key 反查 Redis 得到 app_id：
- 主凭据 header：``X-App-Key``
- 兜底：``Authorization: Bearer <key>``

Redis 键位：``fangyu:app_keys:{api_key}`` → ``str(app_id)``

由 admin-api 负责在应用创建 / 轮换 Key / 删除应用时维护映射。
Gateway 侧只读，并配合本地进程内缓存降低 Redis 压力。

安全设计：
- 关键决策端点（/v2/decide*）通过 :class:`AppKeyEnforcementMiddleware` 在 body 解析
  之前完成 API Key 校验，未通过直接返回 401，避免 pydantic 校验先触发 422。
- 校验成功后把 ``ResolvedAppKey`` 写入 ``request.state.resolved_app_key``，
  路由层用 :func:`require_app_key` 依赖再取用。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import Request
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from fangyu_shared.exceptions import AuthenticationException
from fangyu_shared.logging import get_logger

_logger = get_logger("gateway.app_key")


@dataclass(slots=True)
class ResolvedAppKey:
    """API Key 校验成功后的解析结果。"""

    app_id: int
    api_key: str


class AppKeyResolver:
    """API Key → app_id 解析器，带本地 TTL 缓存。"""

    def __init__(
        self,
        redis: Redis,
        *,
        key_prefix: str = "fangyu:app_keys:",
        cache_ttl: int = 60,
        max_cache_size: int = 4096,
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix
        self._cache_ttl = max(cache_ttl, 0)
        self._max_cache_size = max_cache_size
        self._cache: dict[str, tuple[int, float]] = {}

    async def resolve(self, api_key: str) -> int | None:
        """把 api_key 反查成 app_id。未命中返回 None。"""
        if not api_key:
            return None

        cached = self._cache_get(api_key)
        if cached is not None:
            return cached

        raw: Any = await self._redis.get(self._prefix + api_key)
        if raw is None:
            return None

        try:
            app_id = int(raw)
        except (TypeError, ValueError):
            _logger.warning("app_key_mapping_invalid", api_key_prefix=api_key[:6], value=str(raw))
            return None

        if app_id <= 0:
            return None

        self._cache_set(api_key, app_id)
        return app_id

    def invalidate(self, api_key: str) -> None:
        """在测试或 admin 侧回调时可主动清缓存。"""
        self._cache.pop(api_key, None)

    def clear(self) -> None:
        self._cache.clear()

    def _cache_get(self, key: str) -> int | None:
        if self._cache_ttl <= 0:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        if expire_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: int) -> None:
        if self._cache_ttl <= 0:
            return
        if len(self._cache) >= self._max_cache_size:
            self._cache.pop(next(iter(self._cache)), None)
        self._cache[key] = (value, time.monotonic() + self._cache_ttl)


def extract_api_key(request: Request, *, header_name: str = "X-App-Key") -> str | None:
    """按优先级从请求中提取 API Key。"""
    key = request.headers.get(header_name)
    if key:
        return key.strip()
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


class AppKeyEnforcementMiddleware(BaseHTTPMiddleware):
    """在到达路由 body 解析之前拦截，完成 API Key 校验。

    - 只对配置的 ``protected_patterns`` 生效，默认覆盖 ``/v2/decide*``
      与 ``/v2/rule/test``。后者会回显规则命中逻辑，若不鉴权等于把规则
      边界开放给外部试探，因此与决策接口同级保护。
    - 未通过校验直接返回 401，格式与 shared 异常处理器保持一致。
    - 通过后把 :class:`ResolvedAppKey` 写入 ``request.state.resolved_app_key``。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        resolver_provider: Any,
        settings_provider: Any,
        protected_patterns: Iterable[str] = (
            r"^/v2/decide(?:/|$)",
            r"^/v2/rule/test(?:/|$)",
        ),
    ) -> None:
        super().__init__(app)
        self._resolver_provider = resolver_provider
        self._settings_provider = settings_provider
        self._patterns = [re.compile(p) for p in protected_patterns]

    def _needs_guard(self, path: str) -> bool:
        return any(p.search(path) for p in self._patterns)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.method == "OPTIONS" or not self._needs_guard(request.url.path):
            return await call_next(request)

        settings = self._settings_provider()

        if not settings.app_key_required:
            raw_key = extract_api_key(request, header_name=settings.app_key_header) or ""
            request.state.resolved_app_key = ResolvedAppKey(app_id=0, api_key=raw_key)
            return await call_next(request)

        api_key = extract_api_key(request, header_name=settings.app_key_header)
        if not api_key:
            return _auth_failure_response(request, "缺少 API Key")

        try:
            resolver = self._resolver_provider()
            app_id = await resolver.resolve(api_key)
        except Exception as exc:  # pragma: no cover - Redis 异常兜底
            _logger.error("app_key_resolve_error", error=str(exc))
            return _auth_failure_response(request, "API Key 校验失败", code="APP_KEY_RESOLVE_ERROR")

        if app_id is None:
            return _auth_failure_response(request, "API Key 无效或已失效")

        request.state.resolved_app_key = ResolvedAppKey(app_id=app_id, api_key=api_key)
        return await call_next(request)


def _auth_failure_response(
    request: Request,
    message: str,
    *,
    code: str = "AUTH_UNAUTHENTICATED",
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return JSONResponse(
        status_code=401,
        content={
            "code": code,
            "message": message,
            "details": {},
            "request_id": request_id,
        },
    )


async def require_app_key(request: Request) -> ResolvedAppKey:
    """FastAPI 依赖：从 :class:`AppKeyEnforcementMiddleware` 已写入的 state 中取结果。

    若 middleware 未生效（例如未挂载），会尝试即时校验，保证行为一致。
    """
    resolved: ResolvedAppKey | None = getattr(request.state, "resolved_app_key", None)
    if resolved is not None:
        return resolved

    # 兜底路径：middleware 未介入（如本地脚本直接调用 decide 依赖）。
    from src.interfaces.http.dependencies import (
        get_app_key_resolver,
        get_gateway_settings,
    )

    settings = get_gateway_settings()

    if not settings.app_key_required:
        raw_key = extract_api_key(request, header_name=settings.app_key_header) or ""
        return ResolvedAppKey(app_id=0, api_key=raw_key)

    api_key = extract_api_key(request, header_name=settings.app_key_header)
    if not api_key:
        raise AuthenticationException("缺少 API Key")

    app_id = await get_app_key_resolver().resolve(api_key)
    if app_id is None:
        raise AuthenticationException("API Key 无效或已失效")

    return ResolvedAppKey(app_id=app_id, api_key=api_key)


__all__ = [
    "AppKeyResolver",
    "AppKeyEnforcementMiddleware",
    "ResolvedAppKey",
    "extract_api_key",
    "require_app_key",
]

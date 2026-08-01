"""登录限流中间件。

防止暴力破解攻击，对 POST /v2/auth/login 按 username + ip 限流。
- 60 秒内最多 5 次尝试
- 超限返回 429 + Retry-After header
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from fangyu_shared.logging import get_logger

from src.infrastructure.rate_limiter import RateLimiter

_logger = get_logger("admin.login_rate_limit")

_LOGIN_PATH = "/v2/auth/login"
_LIMIT = 5
_WINDOW_SEC = 60


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "POST" or request.url.path != _LOGIN_PATH:
            return await call_next(request)

        body = await request.body()
        try:
            import json
            data = json.loads(body) if body else {}
            username = data.get("username", "")
        except Exception:
            username = ""

        ip = _client_ip(request)
        key = f"login:{ip}:{username}"

        allowed, retry_after = await self._limiter.is_allowed(
            key, limit=_LIMIT, window_sec=_WINDOW_SEC
        )

        if not allowed:
            _logger.warning(
                "login_rate_limited",
                username=username,
                ip=ip,
                window_sec=_WINDOW_SEC,
                limit=_LIMIT,
            )
            return JSONResponse(
                status_code=429,
                content={"error": "登录频率超限，请稍后重试"},
                headers={"Retry-After": str(retry_after)},
            )

        request.state._login_body = body
        return await call_next(request)


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

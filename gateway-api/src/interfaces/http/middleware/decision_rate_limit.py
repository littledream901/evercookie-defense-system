"""决策 API 限流中间件。

防止 SDK 被滥刷，对 POST /v2/decide 及其子路径（含 /v2/decide/fast）限流。
- 限流主体优先取 app_id，退化顺序见 ``_limit_subject``
- 60 秒内最多 100 次
- 超限返回 429 + Retry-After header

注意：本中间件必须挂在 AppKeyEnforcementMiddleware **之内**（即先于它
add_middleware），否则读不到 ``request.state.resolved_app_key``。
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from fangyu_shared.logging import get_logger


_logger = get_logger("gateway.decision_rate_limit")

_DECIDE_PATH_RE = re.compile(r"^/v2/decide(?:/|$)")
_LIMIT = 100
_WINDOW_SEC = 60


class DecisionRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, redis: Any | Callable[[], Any]) -> None:
        super().__init__(app)
        self._redis = redis

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "POST" or not _DECIDE_PATH_RE.search(request.url.path):
            return await call_next(request)

        app_key = self._limit_subject(request)
        if not app_key:
            return await call_next(request)

        key = f"decide:{app_key}"
        allowed, retry_after = await self._is_allowed(key)

        if not allowed:
            _logger.warning(
                "decision_rate_limited",
                app_key=app_key,
                window_sec=_WINDOW_SEC,
                limit=_LIMIT,
            )
            return JSONResponse(
                status_code=429,
                content={"error": "决策频率超限，请稍后重试"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    @staticmethod
    def _limit_subject(request: Request) -> str | None:
        """取限流主体。

        优先用 AppKeyEnforcementMiddleware 写入的 ``resolved_app_key``；
        它在本中间件之前执行，所以此处一定拿得到。
        当站点关闭强校验（app_key_required=False）时 app_id 为 0，
        退化成按原始 key 限流；连 key 都没有则按客户端 IP 兜底，
        避免匿名流量完全不受约束。
        """
        resolved = getattr(request.state, "resolved_app_key", None)
        if resolved is not None:
            if getattr(resolved, "app_id", 0):
                return f"app:{resolved.app_id}"
            raw = getattr(resolved, "api_key", "") or ""
            if raw:
                return f"key:{raw}"

        legacy = getattr(request.state, "app_key", None)
        if legacy:
            return f"key:{legacy}"

        client = request.client
        return f"ip:{client.host}" if client and client.host else None

    async def _is_allowed(self, key: str) -> tuple[bool, int]:
        now = time.time()
        window_start = now - _WINDOW_SEC
        redis = self._redis() if callable(self._redis) else self._redis
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(uuid.uuid4()): now})
        pipe.zcard(key)
        pipe.expire(key, _WINDOW_SEC + 10)
        results = await pipe.execute()
        count = results[2]
        allowed = count <= _LIMIT
        retry_after = 0 if allowed else _WINDOW_SEC
        return allowed, retry_after

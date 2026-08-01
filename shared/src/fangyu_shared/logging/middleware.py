"""FastAPI/Starlette 请求上下文中间件。

职责：
- 为每个请求生成 request_id（或复用上游 X-Request-ID）
- 绑定 app_id、path、method 等上下文变量
- 在响应头回写 X-Request-ID，方便链路排查
- 记录访问日志（含耗时、状态码）
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from fangyu_shared.logging.context import bind_request_context, clear_request_context
from fangyu_shared.logging.logger import get_logger

_logger = get_logger("fangyu.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件。"""

    def __init__(
        self,
        app: Any,
        *,
        header_name: str = "X-Request-ID",
        access_log: bool = True,
    ) -> None:
        super().__init__(app)
        self._header = header_name
        self._access_log = access_log

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get(self._header) or uuid.uuid4().hex
        app_id = request.headers.get("X-App-ID")
        bind_request_context(
            request_id=rid,
            app_id=app_id,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[self._header] = rid
            return response
        finally:
            if self._access_log:
                _logger.info(
                    "http_access",
                    status_code=status_code,
                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                )
            clear_request_context()

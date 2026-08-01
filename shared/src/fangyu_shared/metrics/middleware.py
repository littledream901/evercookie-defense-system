"""HTTP 指标中间件。

自动记录每个请求的次数与耗时，避免各服务重复实现。
路径会经过归一化，避免高基数（如 /apps/{id} 全都合并到一个 label）。
"""

from __future__ import annotations

import re
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from fangyu_shared.metrics.registry import (
    http_request_duration_seconds,
    http_requests_total,
)

_DIGIT_SEG = re.compile(r"/\d+")
_UUID_SEG = re.compile(r"/[0-9a-fA-F-]{8,}")


def _normalize_path(path: str) -> str:
    path = _DIGIT_SEG.sub("/{id}", path)
    path = _UUID_SEG.sub("/{uuid}", path)
    return path or "/"


class PrometheusMiddleware(BaseHTTPMiddleware):
    """将 HTTP 请求耗时/计数写入 Prometheus。"""

    def __init__(self, app: Any, *, service_name: str) -> None:
        super().__init__(app)
        self._service = service_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            path = _normalize_path(request.url.path)
            duration = time.perf_counter() - start
            http_requests_total.labels(
                service=self._service,
                method=request.method,
                path=path,
                status=str(status),
            ).inc()
            http_request_duration_seconds.labels(
                service=self._service,
                method=request.method,
                path=path,
            ).observe(duration)

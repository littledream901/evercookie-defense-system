"""健康检查与探针接口。"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from fangyu_shared.clickhouse_manager import ClickHouseManager
from fangyu_shared.metrics import metrics_endpoint
from fangyu_shared.redis_manager import RedisManager
from fangyu_shared.schemas.common import HealthCheckResponse

from src.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness 探针")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=HealthCheckResponse, summary="Readiness 探针")
async def readiness() -> HealthCheckResponse:
    settings = get_settings()
    deps: dict[str, str] = {}
    deps["redis"] = "ok" if await RedisManager.ping() else "fail"
    if ClickHouseManager.is_initialized():
        deps["clickhouse"] = "ok" if await ClickHouseManager.ping() else "fail"
    return HealthCheckResponse(
        service=settings.service_name,
        version=settings.version,
        dependencies=deps,
    )


@router.get("/metrics", summary="Prometheus 指标")
async def metrics() -> Response:
    body, content_type = metrics_endpoint()
    return Response(content=body, media_type=content_type, status_code=status.HTTP_200_OK)

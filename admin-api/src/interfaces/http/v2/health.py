"""健康检查路由：liveness / readiness。"""

from __future__ import annotations

from fangyu_shared.clickhouse_manager import ClickHouseManager
from fangyu_shared.metrics import metrics_endpoint
from fangyu_shared.redis_manager import RedisManager
from fangyu_shared.schemas.common import HealthCheckResponse, SuccessResponse
from fangyu_shared.utils.time import local_now
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text

from src.config import AdminSettings
from src.infrastructure.database import Database
from src.interfaces.http.dependencies import get_settings_dep

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=SuccessResponse[HealthCheckResponse])
async def healthz(
    settings: AdminSettings = Depends(get_settings_dep),
) -> SuccessResponse[HealthCheckResponse]:
    return SuccessResponse(
        data=HealthCheckResponse(
            service=settings.service_name,
            status="ok",
            version=settings.version,
            checked_at=local_now(),
        )
    )


@router.get(
    "/readyz",
    response_model=SuccessResponse[HealthCheckResponse],
    responses={503: {"description": "依赖不可用"}},
)
async def readyz(
    response: Response,
    settings: AdminSettings = Depends(get_settings_dep),
) -> SuccessResponse[HealthCheckResponse]:
    deps: dict[str, str] = {}

    try:
        redis_client = RedisManager.get_client()
        await redis_client.ping()
        deps["redis"] = "ok"
    except Exception as exc:  # pragma: no cover - 状态字符串
        deps["redis"] = f"error: {exc}"

    try:
        async with Database.session() as session:
            await session.execute(text("SELECT 1"))
        deps["mysql"] = "ok"
    except Exception as exc:  # pragma: no cover
        deps["mysql"] = f"error: {exc}"

    try:
        deps["clickhouse"] = "ok" if await ClickHouseManager.ping() else "down"
    except Exception as exc:  # pragma: no cover
        deps["clickhouse"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return SuccessResponse(
        data=HealthCheckResponse(
            service=settings.service_name,
            status=overall,
            version=settings.version,
            checked_at=local_now(),
            dependencies=deps,
        )
    )


@router.get("/metrics", summary="Prometheus 指标")
async def metrics() -> Response:
    body, content_type = metrics_endpoint()
    return Response(content=body, media_type=content_type, status_code=status.HTTP_200_OK)

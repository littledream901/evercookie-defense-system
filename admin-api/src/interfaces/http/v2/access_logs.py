"""访问日志查询路由。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from fangyu_shared.clickhouse_manager import ClickHouseClient, get_clickhouse
from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.infrastructure.clickhouse.access_log_query import AccessLogQueryService
from src.interfaces.http.dependencies import require_permission

router = APIRouter(prefix="/access-logs", tags=["access-logs"])


def _service(client: ClickHouseClient = Depends(get_clickhouse)) -> AccessLogQueryService:
    return AccessLogQueryService(client)


@router.get(
    "/stats/summary",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def access_log_stats(
    app_id: int = Query(gt=0, alias="appId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    return SuccessResponse(data=await service.stats(app_id=app_id, start=actual_start, end=actual_end))


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def list_access_logs(
    app_id: int = Query(gt=0, alias="appId"),
    start: datetime | None = None,
    end: datetime | None = None,
    request_id: str | None = Query(default=None, alias="requestId"),
    ip: str | None = None,
    fingerprint: str | None = None,
    verdict: str | None = None,
    mechanism: str | None = None,
    decided_by: str | None = Query(default=None, alias="decidedBy"),
    country: str | None = None,
    device_type: str | None = Query(default=None, alias="deviceType"),
    crawler_category: str | None = Query(default=None, alias="crawlerCategory"),
    connection_type: str | None = Query(default=None, alias="connectionType"),
    path: str | None = None,
    is_bot: bool | None = Query(default=None, alias="isBot"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500, alias="pageSize"),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[PageResponse[dict[str, Any]]]:
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows, total = await service.list_paged(
        app_id=app_id,
        start=actual_start,
        end=actual_end,
        filters={
            "request_id": request_id or "",
            "ip": ip or "",
            "fingerprint": fingerprint or "",
            "verdict": verdict or "",
            "mechanism": mechanism or "",
            "decided_by": decided_by or "",
            "country": country or "",
            "device_type": device_type or "",
            "crawler_category": crawler_category or "",
            "connection_type": connection_type or "",
            "path": path or "",
        },
        is_bot=is_bot,
        page=page,
        page_size=page_size,
    )
    return SuccessResponse(data=PageResponse(items=rows, total=total, page=page, pageSize=page_size))


@router.get(
    "/{request_id}",
    response_model=SuccessResponse[dict[str, Any] | None],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def get_access_log(
    request_id: str,
    app_id: int = Query(gt=0, alias="appId"),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[dict[str, Any] | None]:
    row = await service.get_by_request_id(app_id=app_id, request_id=request_id)
    return SuccessResponse(data=row)

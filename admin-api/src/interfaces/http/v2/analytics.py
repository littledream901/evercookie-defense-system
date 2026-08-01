"""分析查询路由：时序 / 处置分布 / TopN。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.analytics_service import AnalyticsService
from src.domain.analytics.query_spec import (
    AnalyticsQuerySpec,
    DecisionTimelineSpec,
    DispositionBreakdownSpec,
    TopEntitySpec,
)
from src.interfaces.http.dependencies import (
    get_analytics_service,
    require_permission,
)

from .schemas import AnalyticsBaseRequest, TimelineRequest, TopEntityRequest

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _base(payload: AnalyticsBaseRequest) -> AnalyticsQuerySpec:
    return AnalyticsQuerySpec(
        app_id=payload.app_id,
        start=payload.start,
        end=payload.end,
        filters=dict(payload.filters),
    )


@router.post(
    "/timeline",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def timeline(
    payload: TimelineRequest,
    service: AnalyticsService = Depends(get_analytics_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    spec = DecisionTimelineSpec(base=_base(payload), granularity=payload.granularity)
    rows = await service.get_timeline(spec)
    return SuccessResponse(data=rows)


@router.post(
    "/disposition-breakdown",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def disposition_breakdown(
    payload: AnalyticsBaseRequest,
    service: AnalyticsService = Depends(get_analytics_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    spec = DispositionBreakdownSpec(base=_base(payload))
    rows = await service.get_disposition_breakdown(spec)
    return SuccessResponse(data=rows)


@router.post(
    "/top-entities",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def top_entities(
    payload: TopEntityRequest,
    service: AnalyticsService = Depends(get_analytics_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    spec = TopEntitySpec(
        base=_base(payload), dimension=payload.dimension, limit=payload.limit
    )
    rows = await service.get_top_entities(spec)
    return SuccessResponse(data=rows)

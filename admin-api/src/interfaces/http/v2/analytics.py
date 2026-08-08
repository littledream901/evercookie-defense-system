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
    RuleHitRateSpec,
    TopEntitySpec,
)
from src.interfaces.http.dependencies import (
    get_analytics_service,
    require_permission,
)

from .schemas import (
    AnalyticsBaseRequest,
    RuleHitRateRequest,
    TimelineRequest,
    TopEntityRequest,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _base(payload: AnalyticsBaseRequest) -> AnalyticsQuerySpec:
    """构建分析查询基础参数。

    Args:
        payload.site_id: 站点 ID，对应 ClickHouse decision_events 的站点维度列。

    Note:
        TODO(V3 改名): SQL 已按目标列名 site_id 生成，ClickHouse DDL 的
        app_id → site_id 改名由另一个任务负责，两边需同批次上线。
        应用级聚合查询需要在上层实现（先查询应用下的站点列表）。
    """
    return AnalyticsQuerySpec(
        site_id=payload.site_id,
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
    spec = DecisionTimelineSpec(
        base=_base(payload),
        granularity=payload.granularity,
        dimension=payload.dimension,
    )
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


@router.post(
    "/rule-hit-rate",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def rule_hit_rate(
    payload: RuleHitRateRequest,
    service: AnalyticsService = Depends(get_analytics_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """规则命中率。

    返回每条规则的命中数、按裁决拆分的分布、加权平均分与恶意率，按命中数降序。
    ``rule_name`` 不在此返回（规则元数据在 Postgres，跨库取不到），前端用
    rule_id 与规则列表做本地映射。
    """
    spec = RuleHitRateSpec(
        site_id=payload.site_id,
        start=payload.start,
        end=payload.end,
        limit=payload.limit,
    )
    rows = await service.get_rule_hit_rate(spec)
    return SuccessResponse(data=rows)

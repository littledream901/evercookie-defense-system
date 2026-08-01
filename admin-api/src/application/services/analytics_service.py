"""分析服务。"""

from __future__ import annotations

from typing import Any

from src.domain.analytics.query_spec import (
    DecisionTimelineSpec,
    DispositionBreakdownSpec,
    TopEntitySpec,
)
from src.infrastructure.clickhouse.analytics_query import AnalyticsQueryService


class AnalyticsService:
    def __init__(self, query_service: AnalyticsQueryService) -> None:
        self._query = query_service

    async def get_timeline(self, spec: DecisionTimelineSpec) -> list[dict[str, Any]]:
        return await self._query.query_timeline(spec)

    async def get_disposition_breakdown(self, spec: DispositionBreakdownSpec) -> list[dict[str, Any]]:
        return await self._query.query_disposition_breakdown(spec)

    async def get_top_entities(self, spec: TopEntitySpec) -> list[dict[str, Any]]:
        return await self._query.query_top_entities(spec)

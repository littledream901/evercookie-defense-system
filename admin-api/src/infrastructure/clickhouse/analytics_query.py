"""ClickHouse 分析查询：将领域 QuerySpec 翻译为 SQL 并返回结构化数据。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fangyu_shared.clickhouse_manager import ClickHouseClient

from src.domain.analytics.query_spec import (
    DecisionTimelineSpec,
    DispositionBreakdownSpec,
    TopEntitySpec,
)


class AnalyticsQueryService:
    """决策事件分析查询。"""

    def __init__(self, client: ClickHouseClient) -> None:
        self._client = client

    def _build_where(self, app_id: int | None, start: datetime, end: datetime, filters: dict[str, str]) -> tuple[str, dict[str, Any]]:
        clauses = [
            "occurred_at >= toDateTime({start})",
            "occurred_at < toDateTime({end})",
        ]
        params: dict[str, Any] = {
            "start": self._format_dt(start),
            "end": self._format_dt(end),
        }
        if app_id is not None:
            clauses.insert(0, "app_id = {app_id}")
            params["app_id"] = app_id
        if filters.get("verdict"):
            clauses.append("verdict = {verdict}")
            params["verdict"] = filters["verdict"]
        if filters.get("mechanism"):
            clauses.append("mechanism = {mechanism}")
            params["mechanism"] = filters["mechanism"]
        if filters.get("decided_by"):
            clauses.append("decided_by = {decided_by}")
            params["decided_by"] = filters["decided_by"]
        if filters.get("device_type"):
            clauses.append("device_type = {device_type}")
            params["device_type"] = filters["device_type"]
        if filters.get("country"):
            clauses.append("country = {country}")
            params["country"] = filters["country"]
        if filters.get("fingerprint"):
            clauses.append("fingerprint = {fingerprint}")
            params["fingerprint"] = filters["fingerprint"]
        if filters.get("ip"):
            clauses.append("ip = {ip}")
            params["ip"] = filters["ip"]
        if filters.get("path"):
            clauses.append("path = {path}")
            params["path"] = filters["path"]
        return " AND ".join(clauses), params

    async def query_timeline(self, spec: DecisionTimelineSpec) -> list[dict[str, Any]]:
        interval = self._interval_for(spec.granularity)
        where_sql, params = self._build_where(
            spec.base.app_id,
            spec.base.start,
            spec.base.end,
            spec.base.filters,
        )
        sql = f"""
        SELECT
            toStartOfInterval(occurred_at, INTERVAL 1 {interval}) AS bucket,
            verdict,
            mechanism,
            count(*) AS count
        FROM fangyu.decision_events
        WHERE {where_sql}
        GROUP BY bucket, verdict, mechanism
        ORDER BY bucket, verdict, mechanism
        """
        return await self._client.fetch(sql, params)

    async def query_disposition_breakdown(self, spec: DispositionBreakdownSpec) -> list[dict[str, Any]]:
        where_sql, params = self._build_where(
            spec.base.app_id,
            spec.base.start,
            spec.base.end,
            spec.base.filters,
        )
        # 处置已拆为 verdict（裁决）+ mechanism（机制）两个维度，
        # 拼接成 "verdict/mechanism" 供图表展示单一标签
        sql = f"""
        SELECT
            concat(verdict, '/', mechanism) AS disposition,
            verdict,
            mechanism,
            count(*) AS count
        FROM fangyu.decision_events
        WHERE {where_sql}
        GROUP BY verdict, mechanism
        ORDER BY count DESC
        """
        return await self._client.fetch(sql, params)

    async def query_top_entities(self, spec: TopEntitySpec) -> list[dict[str, Any]]:
        field = self._field_for_dimension(spec.dimension)
        where_sql, params = self._build_where(
            spec.base.app_id,
            spec.base.start,
            spec.base.end,
            spec.base.filters,
        )
        sql = f"""
        SELECT
            {field} AS entity,
            count(*) AS count
        FROM fangyu.decision_events
        WHERE {where_sql}
          AND {field} != ''
        GROUP BY entity
        ORDER BY count DESC
        LIMIT {spec.limit}
        """
        return await self._client.fetch(sql, params)

    @staticmethod
    def _interval_for(granularity: str) -> str:
        mapping = {"minute": "MINUTE", "hour": "HOUR", "day": "DAY"}
        return mapping.get(granularity, "HOUR")

    @staticmethod
    def _field_for_dimension(dimension: str) -> str:
        mapping = {
            "ip": "ip",
            "device": "fingerprint",
            "country": "country",
            "decided_by": "decided_by",
            "mechanism": "mechanism",
            "verdict": "verdict",
        }
        return mapping.get(dimension, "ip")

    @staticmethod
    def _format_dt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

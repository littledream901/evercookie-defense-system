"""访问日志 ClickHouse 查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fangyu_shared.clickhouse_manager import ClickHouseClient

_SELECT_COLUMNS = """
    event_id, app_id, fingerprint, device_id, ip, ip_type, user_agent,
    path, referer, method,
    verdict, mechanism, target_kind, target_url, http_status,
    decided_by, decided_stage, decided_rule_id,
    score, scorer_scores, rule_ids, reason,
    country, asn, connection_type,
    device_type, os_name, browser_name, is_bot, crawler_category, crawler_vendor,
    repeat_key, repeat_value, evercookie_restore,
    shadow_rule_ids, shadow_verdicts,
    decision_cost_ms, request_id, occurred_at, schema_version, event_version
"""

_FILTERABLE = (
    "request_id",
    "ip",
    "fingerprint",
    "verdict",
    "mechanism",
    "decided_by",
    "path",
    "country",
    "device_type",
    "crawler_category",
    "connection_type",
    "repeat_value",
)
"""白名单：可作为等值过滤条件的列。

只允许白名单内的列名拼进 SQL，值一律走参数化占位符，避免 SQL 注入。
"""


class AccessLogQueryService:
    def __init__(self, client: ClickHouseClient) -> None:
        self._client = client

    async def list_paged(
        self,
        *,
        app_id: int,
        start: datetime,
        end: datetime,
        filters: dict[str, str] | None = None,
        is_bot: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        where_sql, params = self._where(
            app_id=app_id, start=start, end=end, filters=filters, is_bot=is_bot
        )
        params["limit"] = page_size
        params["offset"] = max(0, (page - 1) * page_size)
        rows = await self._client.fetch(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM fangyu.decision_events
            WHERE {where_sql}
            ORDER BY occurred_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        total_row = await self._client.fetch_one(
            f"SELECT count(*) AS total FROM fangyu.decision_events WHERE {where_sql}",
            params,
        )
        return rows, int((total_row or {}).get("total", 0))

    async def get_by_request_id(self, *, app_id: int, request_id: str) -> dict[str, Any] | None:
        rows = await self._client.fetch(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM fangyu.decision_events
            WHERE app_id = %(app_id)s AND request_id = %(request_id)s
            ORDER BY occurred_at DESC
            LIMIT 1
            """,
            {"app_id": app_id, "request_id": request_id},
        )
        return rows[0] if rows else None

    async def get_traces(self, *, app_id: int, request_id: str) -> list[dict[str, Any]]:
        """取某次请求的规则条件命中明细（冷表，TTL 7 天，可能已过期）。"""
        return await self._client.fetch(
            """
            SELECT rule_id, rule_name, field, op, expected, actual, matched
            FROM fangyu.decision_traces
            WHERE app_id = %(app_id)s AND request_id = %(request_id)s
            ORDER BY rule_id
            """,
            {"app_id": app_id, "request_id": request_id},
        )

    async def stats(self, *, app_id: int, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return await self._client.fetch(
            """
            SELECT verdict, mechanism, decided_by,
                   count(*) AS count, avg(score) AS avg_score,
                   avg(decision_cost_ms) AS avg_cost_ms
            FROM fangyu.decision_events
            WHERE app_id = %(app_id)s
              AND occurred_at >= %(start)s
              AND occurred_at < %(end)s
            GROUP BY verdict, mechanism, decided_by
            ORDER BY count DESC
            """,
            {"app_id": app_id, "start": self._format_dt(start), "end": self._format_dt(end)},
        )

    async def device_breakdown(
        self, *, app_id: int, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """设备维度分布。依赖落库的 UA 解析结果，存原文时无法实现此查询。"""
        return await self._client.fetch(
            """
            SELECT device_type, os_name, browser_name, is_bot,
                   count(*) AS count,
                   countIf(verdict = 'hostile') AS hostile_count
            FROM fangyu.decision_events
            WHERE app_id = %(app_id)s
              AND occurred_at >= %(start)s
              AND occurred_at < %(end)s
            GROUP BY device_type, os_name, browser_name, is_bot
            ORDER BY count DESC
            LIMIT 100
            """,
            {"app_id": app_id, "start": self._format_dt(start), "end": self._format_dt(end)},
        )

    async def shadow_impact(
        self, *, app_id: int, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """影子规则影响面：发布前测算「这条草稿规则会多拦多少流量」。"""
        return await self._client.fetch(
            """
            SELECT arrayJoin(shadow_rule_ids) AS shadow_rule_id,
                   count(*) AS would_hit_count,
                   countIf(mechanism = 'pass') AS currently_passed_count
            FROM fangyu.decision_events
            WHERE app_id = %(app_id)s
              AND occurred_at >= %(start)s
              AND occurred_at < %(end)s
              AND notEmpty(shadow_rule_ids)
            GROUP BY shadow_rule_id
            ORDER BY would_hit_count DESC
            """,
            {"app_id": app_id, "start": self._format_dt(start), "end": self._format_dt(end)},
        )

    @staticmethod
    def _where(
        *,
        app_id: int,
        start: datetime,
        end: datetime,
        filters: dict[str, str] | None,
        is_bot: bool | None,
    ) -> tuple[str, dict[str, Any]]:
        clauses = [
            "app_id = %(app_id)s",
            "occurred_at >= %(start)s",
            "occurred_at < %(end)s",
        ]
        params: dict[str, Any] = {
            "app_id": app_id,
            "start": AccessLogQueryService._format_dt(start),
            "end": AccessLogQueryService._format_dt(end),
        }
        for name, value in (filters or {}).items():
            if name not in _FILTERABLE or not value:
                continue
            clauses.append(f"{name} = %({name})s")
            params[name] = value
        if is_bot is not None:
            clauses.append("is_bot = %(is_bot)s")
            params["is_bot"] = 1 if is_bot else 0
        return " AND ".join(clauses), params

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

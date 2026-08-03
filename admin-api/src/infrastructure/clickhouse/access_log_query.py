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
    accept_language,
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
        # 从客户端配置读取实际库名，避免硬编码
        self._db = client.database

    async def list_paged(
        self,
        *,
        app_id: int | None,
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
            FROM {self._db}.decision_events
            WHERE {where_sql}
            ORDER BY occurred_at DESC
            LIMIT {{limit}} OFFSET {{offset}}
            """,
            params,
        )
        total_row = await self._client.fetch_one(
            f"SELECT count(*) AS total FROM {self._db}.decision_events WHERE {where_sql}",
            params,
        )
        return rows, int((total_row or {}).get("total", 0))

    async def get_by_request_id(self, *, app_id: int | None, request_id: str) -> dict[str, Any] | None:
        app_clause = "app_id = {app_id} AND " if app_id is not None else ""
        params: dict[str, Any] = {"request_id": request_id}
        if app_id is not None:
            params["app_id"] = app_id
        rows = await self._client.fetch(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM {self._db}.decision_events
            WHERE {app_clause}request_id = {{request_id}}
            ORDER BY occurred_at DESC
            LIMIT 1
            """,
            params,
        )
        return rows[0] if rows else None

    async def get_traces(self, *, app_id: int | None, request_id: str) -> list[dict[str, Any]]:
        """取某次请求的规则条件命中明细（冷表，TTL 7 天，可能已过期）。"""
        app_clause = "app_id = {app_id} AND " if app_id is not None else ""
        params: dict[str, Any] = {"request_id": request_id}
        if app_id is not None:
            params["app_id"] = app_id
        return await self._client.fetch(
            f"""
            SELECT rule_id, rule_name, field, op, expected, actual, matched
            FROM {self._db}.decision_traces
            WHERE {app_clause}request_id = {{request_id}}
            ORDER BY rule_id
            """,
            params,
        )

    async def stats(self, *, app_id: int | None, start: datetime, end: datetime) -> list[dict[str, Any]]:
        app_clause = "app_id = {app_id} AND " if app_id is not None else ""
        params: dict[str, Any] = {"start": self._format_dt(start), "end": self._format_dt(end)}
        if app_id is not None:
            params["app_id"] = app_id
        return await self._client.fetch(
            f"""
            SELECT verdict, mechanism, decided_by,
                   count(*) AS count, avg(score) AS avg_score,
                   avg(decision_cost_ms) AS avg_cost_ms
            FROM {self._db}.decision_events
            WHERE {app_clause}occurred_at >= {{start}}
              AND occurred_at < {{end}}
            GROUP BY verdict, mechanism, decided_by
            ORDER BY count DESC
            """,
            params,
        )

    async def device_breakdown(
        self, *, app_id: int, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """设备维度分布。依赖落库的 UA 解析结果，存原文时无法实现此查询。"""
        return await self._client.fetch(
            f"""
            SELECT device_type, os_name, browser_name, is_bot,
                   count(*) AS count,
                   countIf(verdict = 'hostile') AS hostile_count
            FROM {self._db}.decision_events
            WHERE app_id = {{app_id}}
              AND occurred_at >= {{start}}
              AND occurred_at < {{end}}
            GROUP BY device_type, os_name, browser_name, is_bot
            ORDER BY count DESC
            LIMIT 100
            """,
            {"app_id": app_id, "start": self._format_dt(start), "end": self._format_dt(end)},
        )

    async def pool_distribution(
        self, *, app_id: int, start: datetime, end: datetime, rule_id: int | None = None
    ) -> list[dict[str, Any]]:
        """轮询地址池命中分布：验证权重/策略是否按预期生效。

        只统计 target_kind='url_pool' 的记录——单地址跳转（kind='url'）混进来
        会让分布图出现一个占绝对多数的「地址」，把真正的池内比例压成噪音。

        rule_id 可选：不传时按 app 汇总。多条规则各有地址池时汇总没有意义，
        前端应当带上 rule_id。
        """
        clauses = [
            "app_id = {app_id}",
            "occurred_at >= {start}",
            "occurred_at < {end}",
            "target_kind = 'url_pool'",
            "notEmpty(target_url)",
        ]
        params: dict[str, Any] = {
            "app_id": app_id,
            "start": self._format_dt(start),
            "end": self._format_dt(end),
        }
        if rule_id is not None:
            clauses.append("has(rule_ids, {rule_id})")
            params["rule_id"] = rule_id
        return await self._client.fetch(
            f"""
            SELECT target_url,
                   count(*) AS hit_count,
                   countIf(http_status >= 400) AS error_count,
                   min(occurred_at) AS first_hit_at,
                   max(occurred_at) AS last_hit_at
            FROM {self._db}.decision_events
            WHERE {" AND ".join(clauses)}
            GROUP BY target_url
            ORDER BY hit_count DESC
            LIMIT 64
            """,
            params,
        )

    async def shadow_impact(
        self, *, app_id: int | None, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """影子规则影响面：发布前测算「这条草稿规则会多拦多少流量」。"""
        app_clause = "app_id = {app_id} AND " if app_id is not None else ""
        params: dict[str, Any] = {"start": self._format_dt(start), "end": self._format_dt(end)}
        if app_id is not None:
            params["app_id"] = app_id
        return await self._client.fetch(
            f"""
            SELECT arrayJoin(shadow_rule_ids) AS shadow_rule_id,
                   count(*) AS would_hit_count,
                   countIf(mechanism = 'pass') AS currently_passed_count
            FROM {self._db}.decision_events
            WHERE {app_clause}occurred_at >= {{start}}
              AND occurred_at < {{end}}
              AND notEmpty(shadow_rule_ids)
            GROUP BY shadow_rule_id
            ORDER BY would_hit_count DESC
            """,
            params,
        )

    @staticmethod
    def _where(
        *,
        app_id: int | None,
        start: datetime,
        end: datetime,
        filters: dict[str, str] | None,
        is_bot: bool | None,
    ) -> tuple[str, dict[str, Any]]:
        clauses = [
            "occurred_at >= {start}",
            "occurred_at < {end}",
        ]
        params: dict[str, Any] = {
            "start": AccessLogQueryService._format_dt(start),
            "end": AccessLogQueryService._format_dt(end),
        }
        # app_id=None 时查全部站点，不加过滤
        if app_id is not None:
            clauses.insert(0, "app_id = {app_id}")
            params["app_id"] = app_id
        for name, value in (filters or {}).items():
            if name not in _FILTERABLE or not value:
                continue
            clauses.append(f"{name} = {{{name}}}")
            params[name] = value
        if is_bot is not None:
            clauses.append("is_bot = {is_bot}")
            params["is_bot"] = 1 if is_bot else 0
        return " AND ".join(clauses), params

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

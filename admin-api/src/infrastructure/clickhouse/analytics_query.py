"""ClickHouse 分析查询：将领域 QuerySpec 翻译为 SQL 并返回结构化数据。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fangyu_shared.clickhouse_manager import ClickHouseClient

from src.domain.analytics.query_spec import (
    DecisionTimelineSpec,
    DispositionBreakdownSpec,
    RuleHitRateSpec,
    TopEntitySpec,
)

_NUMERIC_DIMENSION_FIELDS = frozenset({"is_bot"})
"""数值列维度。这些列不能用 ``!= ''`` 过滤空值，见 query_top_entities。"""


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
        """时序趋势。

        ``dimension='disposition'`` 保持原行为（按 verdict + mechanism 分组）；
        指定爬虫维度时改为按该列分组，用于渲染爬虫流量趋势。两者的返回列不同，
        前端按请求的维度取列即可。
        """
        interval = self._interval_for(spec.granularity)
        where_sql, params = self._build_where(
            spec.base.app_id,
            spec.base.start,
            spec.base.end,
            spec.base.filters,
        )
        group_columns = self._timeline_group_columns(spec.dimension)
        projection = ",\n            ".join(group_columns)
        group_by = ", ".join(group_columns)
        sql = f"""
        SELECT
            toStartOfInterval(occurred_at, INTERVAL 1 {interval}) AS bucket,
            {projection},
            count(*) AS count
        FROM fangyu.decision_events
        WHERE {where_sql}
        GROUP BY bucket, {group_by}
        ORDER BY bucket, {group_by}
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
        # is_bot 是 UInt8，和空串比较在 ClickHouse 里会因类型不匹配报错，
        # 而且「非爬虫」本身就是有意义的取值，不该被当成空值过滤掉。
        empty_guard = "" if field in _NUMERIC_DIMENSION_FIELDS else f"\n          AND {field} != ''"
        # LIMIT 走参数化而非 f-string 插值。此前依赖 Pydantic 的 le=100 兜住，
        # 但那道校验只覆盖 HTTP 入口——服务层直接构造 spec 的调用方绕过它就能
        # 把任意字符串拼进 SQL。值一律参数化，不给「校验漏了一处」留后果。
        params["limit"] = spec.limit
        sql = f"""
        SELECT
            {field} AS entity,
            count(*) AS count
        FROM fangyu.decision_events
        WHERE {where_sql}{empty_guard}
        GROUP BY entity
        ORDER BY count DESC
        LIMIT {{limit}}
        """
        return await self._client.fetch(sql, params)

    async def query_rule_hit_rate(self, spec: RuleHitRateSpec) -> list[dict[str, Any]]:
        """规则命中率：读 ``mv_rule_hits_daily`` 而非扫主表。

        MV 引擎是 ``SummingMergeTree``，后台合并前同一 ``(log_date, app_id,
        rule_id)`` 会存在多份行。直接 ``SELECT hit_count`` 只会拿到某个未合并
        分片的值——不报错，只是数偏小且随合并进度漂移。因此必须 ``GROUP BY``
        + ``sum()``，与 ``fangyu_shared.reputation.aggregator`` 的口径一致。

        ``avg_score`` 在 MV 里是 avg 的结果，SummingMergeTree 会把多份分片的
        平均值**相加**，直接读或再求平均都不对。这里用 ``hit_count`` 加权还原：
        ``sum(avg_score * hit_count) / sum(hit_count)``，等价于把每个分片的
        分数总和相加后除以总条数。

        ``rule_name`` 不在此处补：规则元数据在 Postgres，跨库 JOIN 做不到，
        而为 TopN 结果逐条查库会引入 N+1。调用方需要名称时用返回的 rule_id
        走 ``/v2/rules`` 批量取——规则总数是运营配置量级（几十到几百），
        前端一次性拉全量再本地映射比后端逐条查更省。
        """
        clauses = ["log_date >= toDate({start})", "log_date <= toDate({end})"]
        params: dict[str, Any] = {
            "start": self._format_dt(spec.start),
            "end": self._format_dt(spec.end),
            "limit": spec.limit,
        }
        if spec.app_id is not None:
            clauses.insert(0, "app_id = {app_id}")
            params["app_id"] = spec.app_id
        sql = f"""
        SELECT
            rule_id,
            sum(hit_count)       AS hit_count,
            sum(hostile_count)   AS hostile_count,
            sum(challenge_count) AS challenge_count,
            sum(pass_count)      AS pass_count,
            if(
                sum(hit_count) > 0,
                round(sum(avg_score * hit_count) / sum(hit_count), 2),
                0
            ) AS avg_score,
            if(
                sum(hit_count) > 0,
                round(sum(hostile_count) / sum(hit_count), 4),
                0
            ) AS hostile_rate
        FROM fangyu.mv_rule_hits_daily
        WHERE {" AND ".join(clauses)}
        GROUP BY rule_id
        HAVING hit_count > 0
        ORDER BY hit_count DESC
        LIMIT {{limit}}
        """
        return await self._client.fetch(sql, params)

    @staticmethod
    def _interval_for(granularity: str) -> str:
        mapping = {"minute": "MINUTE", "hour": "HOUR", "day": "DAY"}
        return mapping.get(granularity, "HOUR")

    @staticmethod
    def _timeline_group_columns(dimension: str) -> tuple[str, ...]:
        """时序分组列白名单。

        与 :meth:`_field_for_dimension` 同理：只有映射表里的值才会进 SQL，
        调用方传什么都不会被拼进去。未知维度退回处置分组，保持旧行为。
        """
        mapping: dict[str, tuple[str, ...]] = {
            "disposition": ("verdict", "mechanism"),
            "is_bot": ("is_bot",),
            "crawler_category": ("crawler_category",),
            "crawler_vendor": ("crawler_vendor",),
        }
        return mapping.get(dimension, ("verdict", "mechanism"))

    @staticmethod
    def _field_for_dimension(dimension: str) -> str:
        mapping = {
            "ip": "ip",
            "device": "fingerprint",
            "country": "country",
            "decided_by": "decided_by",
            "mechanism": "mechanism",
            "verdict": "verdict",
            "is_bot": "is_bot",
            "crawler_category": "crawler_category",
            "crawler_vendor": "crawler_vendor",
        }
        return mapping.get(dimension, "ip")

    @staticmethod
    def _format_dt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

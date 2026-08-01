"""事件标准化类型定义."""

from __future__ import annotations

from typing import TypedDict


class NormalizedEvent(TypedDict, total=False):
    """标准化后的访问事件.

    所有字段均 optional，缺失以 None 或空字符串填充，
    便于 ClickHouse 写入与前端展示。
    """

    timestamp: int | None
    request_id: str | None
    site_id: str | None
    app_id: str | None
    device_id: str | None

    dispatch_type: str
    dispatch_label: str

    ip: str | None
    ip_type: str
    ip_type_label: str
    country: str | None
    asn: int | None

    user_agent: str | None
    referer: str | None
    url: str | None
    language: str | None

    risk_score: int | None
    matched_rule_id: str | None
    matched_rule_name: str | None

    cached: bool
    latency_ms: int | None
    extra: dict[str, object]

"""事件上报 / 消费 Schema。

设计要点：存解析结果，而非原料
------------------------------
``user_agent`` 原文对分析毫无用处——不可能在 ClickHouse SQL 里跑 UA 正则。
旧版计算出了 device_type/os/browser 却一个都没落库，导致「移动端拦截率」
这类基础查询做不了。因此本 schema 显式携带 UA parser 与 MMDB 的**解析结果**。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from fangyu_shared.schemas.common import BaseSchema
from fangyu_shared.schemas.disposition import Mechanism, TargetKind, Verdict

# 事件字段协议版本。字段变更时递增（新增可选字段属兼容变更，删除/改类型属破坏变更）。
# v3: 新增 ingress / fingerprint_is_derived / clock_* / behavior_event_count
# v4: 新增 condition_traces（规则条件命中明细，供 worker 写 decision_traces 冷表）
DECISION_EVENT_SCHEMA_VERSION = 4


class ConditionTraceEvent(BaseSchema):
    """规则条件命中明细。

    体量大、查询频率低（只在排障时按 request_id 点查），因此独立成表并
    单独设置更短 TTL，不塞进决策主表。

    ``request_id`` / ``app_id`` / ``occurred_at`` 不在这里带：它们对同一次请求
    的所有明细都相同，随每条重复上报是纯冗余。worker 写库时从所属
    ``DecisionEvent`` 补齐这三列，见 ``TraceTransformer``。
    """

    rule_id: int | None = Field(default=None, alias="ruleId")
    rule_name: str = Field(default="", alias="ruleName", max_length=128)
    field_path: str = Field(default="", alias="field", max_length=64)
    op: str = Field(default="", max_length=24)
    expected: str = Field(default="", max_length=512)
    actual: str = Field(default="", max_length=512)
    matched: bool = False


class DecisionEvent(BaseSchema):
    """写入 Stream / ClickHouse 的决策事件。

    ``schema_version``
        事件字段协议版本，由发布端固定为 :data:`DECISION_EVENT_SCHEMA_VERSION`。

    ``event_version``
        ClickHouse ReplacingMergeTree 用于选出「最新副本」的版本号。默认取
        ``occurred_at`` 的毫秒时间戳，同一 event_id 重复写入时后到达且时间
        戳更大者胜出；worker 侧也会兜底设置。
    """

    event_id: str = Field(..., alias="eventId", max_length=64)
    app_id: int = Field(..., alias="appId", gt=0)
    fingerprint: str = Field(..., max_length=128)
    ingress: str = Field(default="sdk", max_length=16)
    """接入来源：sdk / adapter。两条路径的信号丰富度不同，报表需要分开看。"""
    fingerprint_is_derived: bool = Field(default=False, alias="fingerprintIsDerived")
    """指纹是否为服务端派生。派生指纹区分度低，聚合时应与真指纹分开统计。"""
    device_id: str | None = Field(default=None, alias="deviceId", max_length=128)
    ip: str = Field(..., max_length=64)
    ip_type: str = Field(default="ipv4", alias="ipType")
    user_agent: str = Field(default="", alias="userAgent", max_length=1024)
    host: str = Field(default="", max_length=256)
    """访问的站点域名（从 visit_url 或 HTTP Host 头提取）。"""
    path: str = Field(default="/", max_length=1024)
    referer: str | None = Field(default=None, max_length=2048)
    method: str = Field(default="GET", max_length=16)

    # ── 处置三层 ──
    verdict: Verdict
    mechanism: Mechanism
    target_kind: TargetKind = Field(default=TargetKind.ORIGIN, alias="targetKind")
    target_url: str | None = Field(default=None, alias="targetUrl", max_length=1024)
    http_status: int = Field(default=200, alias="httpStatus", ge=100, le=599)

    # ── 处置溯源：排障第一现场 ──
    decided_by: str = Field(default="system_default", alias="decidedBy", max_length=32)
    decided_stage: str = Field(default="default", alias="decidedStage", max_length=32)
    decided_rule_id: int | None = Field(default=None, alias="decidedRuleId")

    # ── 评分 ──
    score: float = Field(default=0.0)
    scorer_scores: dict[str, float] = Field(default_factory=dict, alias="scorerScores")
    """各 scorer 的原始分。落 ClickHouse Map，可直接在 SQL 里过滤/聚合。"""
    rule_ids: list[int] = Field(default_factory=list, alias="ruleIds")
    reason: str | None = None

    # ── 网络解析结果（MMDB 产物） ──
    country: str | None = Field(default=None, max_length=8)
    asn: int | None = Field(default=None, ge=0)
    asn_org: str | None = Field(default=None, alias="asnOrg", max_length=256)
    """ASN 组织名（如 "The Constant Company" / "China Telecom"），用于运营商/机房展示。"""
    connection_type: str | None = Field(default=None, alias="connectionType", max_length=32)
    is_vpn: bool = Field(default=False, alias="isVpn")
    is_proxy: bool = Field(default=False, alias="isProxy")

    # ── 设备解析结果（UA parser 产物） ──
    device_type: str | None = Field(default=None, alias="deviceType", max_length=32)
    os_name: str | None = Field(default=None, alias="osName", max_length=32)
    browser_name: str | None = Field(default=None, alias="browserName", max_length=32)
    is_bot: bool = Field(default=False, alias="isBot")
    crawler_name: str | None = Field(default=None, alias="crawlerName", max_length=64)
    """爬虫名称（如 "Googlebot"、"Bingbot"）。"""
    crawler_category: str | None = Field(default=None, alias="crawlerCategory", max_length=32)
    crawler_vendor: str | None = Field(default=None, alias="crawlerVendor", max_length=64)

    # ── 请求语言偏好 ──
    accept_language: str | None = Field(default=None, alias="acceptLanguage", max_length=256)
    """Accept-Language 请求头原文，落库供客户端语言分析。"""

    # ── 访客追踪：Evercookie 自愈是本系统的立项理由 ──
    repeat_key: str | None = Field(default=None, alias="repeatKey", max_length=128)
    repeat_value: str | None = Field(default=None, alias="repeatValue", max_length=256)
    evercookie_restore: bool = Field(default=False, alias="evercookieRestore")

    # ── 影子评估：发布前用真实流量测算规则影响面 ──
    shadow_rule_ids: list[int] = Field(default_factory=list, alias="shadowRuleIds")
    shadow_verdicts: list[str] = Field(default_factory=list, alias="shadowVerdicts")

    # ── 规则条件命中明细（采样） ──
    condition_traces: list[ConditionTraceEvent] = Field(
        default_factory=list, alias="conditionTraces", max_length=200
    )
    """规则条件逐条求值明细，由 worker 写入 ``decision_traces`` 冷表。

    只在采样命中时非空（非 trusted 全量 + trusted 抽样），因此绝大多数事件
    这个字段是空列表，不额外占 Stream 带宽。上限 200 与 gateway 侧的收集上限
    一致，防止规则配错时单条事件体积失控。
    """

    # ── Clock：频控计数与封禁 ──
    clock_counts: dict[str, int] = Field(default_factory=dict, alias="clockCounts")
    """各维度各窗口计数，键形如 ``ip_burst``/``fp_short``。

    落 ClickHouse Map，可直接 ``clock_counts['ip_short'] > 100`` 查询，用于
    回答「阈值设多少合适」——没有这份数据，频控阈值只能靠猜。
    """
    clock_banned: bool = Field(default=False, alias="clockBanned")
    behavior_event_count: int = Field(default=0, alias="behaviorEventCount", ge=0)
    """本次请求携带的行为事件数。当前不参与决策，仅用于观测采集端健康度。"""

    # ── 性能 ──
    decision_cost_ms: int = Field(default=0, alias="decisionCostMs", ge=0)

    request_id: str | None = Field(default=None, alias="requestId")
    occurred_at: datetime = Field(default_factory=datetime.utcnow, alias="occurredAt")
    schema_version: int = Field(
        default=DECISION_EVENT_SCHEMA_VERSION,
        alias="schemaVersion",
        ge=1,
    )
    event_version: int = Field(default=0, alias="eventVersion", ge=0)
    extra: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseSchema):
    """批量上报请求。"""

    events: list[DecisionEvent] = Field(default_factory=list, max_length=500)


class EventBatchAck(BaseSchema):
    accepted: int
    rejected: int = 0
    reasons: dict[str, int] = Field(default_factory=dict)

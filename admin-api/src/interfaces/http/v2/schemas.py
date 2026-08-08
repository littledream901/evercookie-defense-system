"""Admin v2 HTTP 层 DTO。

只承担 request/response 序列化职责，业务对象仍由 domain 层持有。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from fangyu_shared.clock.limits import DEFAULT_BAN_SECONDS, MAX_BAN_SECONDS
from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.whitelist.keys import WhitelistDimension
from fangyu_shared.schemas.common import BaseSchema, PageRequest
from fangyu_shared.schemas.disposition import DecisionDisposition, Disposition
from fangyu_shared.schemas.rule import (
    DecisionRule,
    GroupMode,
    RuleCondition,
    RuleKind,
    RulePriority,
)


# ---------- Auth ----------
class LoginRequest(BaseSchema):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseSchema):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseSchema):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenPairSchema(BaseSchema):
    access_token: str
    refresh_token: str
    expires_in: int


class UserBriefSchema(BaseSchema):
    id: int
    username: str
    email: str
    display_name: str
    status: str
    role_ids: list[int] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LoginResponse(BaseSchema):
    user: UserBriefSchema
    tokens: TokenPairSchema
    role_names: list[str]
    permissions: list[str]
    password_change_required: bool = False


class CurrentUserResponse(BaseSchema):
    user: UserBriefSchema
    role_names: list[str]
    permissions: list[str]


# ---------- User ----------
class UserListRequest(PageRequest):
    keyword: str | None = None
    status: Literal["active", "disabled", "locked"] | None = None


class UserCreateRequest(BaseSchema):
    username: str = Field(min_length=2, max_length=64)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=128)
    role_ids: list[int] = Field(default_factory=list)


class UserUpdateRequest(BaseSchema):
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str | None = None
    status: Literal["active", "disabled", "locked"] | None = None


class UserResetPasswordRequest(BaseSchema):
    new_password: str = Field(min_length=8, max_length=128)


class UserAssignRolesRequest(BaseSchema):
    role_ids: list[int] = Field(default_factory=list)


# ---------- API Key ----------
class ApiKeyCreateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=128)


class ApiKeySchema(BaseSchema):
    id: int
    user_id: int
    name: str
    key_prefix: str
    last_used_at: datetime | None = None
    status: str
    created_at: datetime | None = None


class ApiKeyCreatedResponse(BaseSchema):
    key: ApiKeySchema
    api_key: str


# ---------- Role / Permission ----------
class RoleSchema(BaseSchema):
    id: int
    name: str
    description: str
    is_system: bool
    permissions: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleCreateRequest(BaseSchema):
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseSchema):
    description: str | None = None
    permissions: list[str] | None = None


class PermissionSchema(BaseSchema):
    code: str
    description: str


class PermissionUpsertRequest(BaseSchema):
    code: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=255)


# ---------- 接入诊断 ----------
class IngressStatSchema(BaseSchema):
    """单一接入来源（sdk / adapter）的实测指标。"""

    ingress: str
    host: str
    """接入网站域名，用于区分同一站点的多个域名来源。"""
    total: int = 0
    derived_count: int = 0
    """指纹由网关按 IP+UA 派生的请求数；SDK 侧出现即说明埋码未真正采集到指纹。"""
    behavior_count: int = 0
    restore_count: int = 0
    unknown_verdict_count: int = 0
    hostile_count: int = 0
    suspicious_count: int = 0
    clean_count: int = 0
    clock_banned_count: int = 0
    unique_fingerprints: int = 0
    unique_ips: int = 0
    avg_cost_ms: float = 0.0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class IntegrationFindingSchema(BaseSchema):
    """一条可执行的诊断结论。"""

    level: Literal["ok", "warning", "error"]
    code: str
    title: str
    detail: str
    suggestion: str


class IntegrationDiagnosticsSchema(BaseSchema):
    """站点接入诊断结果：配置侧声明 vs 遥测侧实测。"""

    site_id: int
    site_name: str
    domain: str
    is_active: bool
    configured_access_mode: str
    configured_sdk_version: str | None = None
    gateway_url: str | None = None
    window_hours: int
    total_requests: int = 0
    last_seen_at: datetime | None = None
    status: Literal["ok", "warning", "error", "no_data"]
    ingress_stats: list[IngressStatSchema] = Field(default_factory=list)
    findings: list[IntegrationFindingSchema] = Field(default_factory=list)


# ---------- Rule ----------
class RuleListRequest(PageRequest):
    keyword: str | None = None
    status: Literal["draft", "published", "disabled", "archived"] | None = None


class RuleUpsertRequest(BaseSchema):
    """规则新建/编辑请求。

    每条规则均为决策规则，命中与未命中各自配置独立处置策略。
    """

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    priority: RulePriority = RulePriority.NORMAL
    conditions: list[RuleCondition] = Field(..., min_length=1)
    match_all: bool = Field(default=True, alias="matchAll")
    group: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list)
    kind: RuleKind = RuleKind.DECISION
    weight: int | None = Field(default=None, ge=-1000, le=1000)
    disposition_match: DecisionDisposition | None = Field(default=None, alias="dispositionMatch")
    """命中时的处置动作，pass 表示立即放行并终止后续规则求值。"""
    disposition_miss: DecisionDisposition | None = Field(default=None, alias="dispositionMiss")
    """未命中时的处置动作，pass 表示放行并继续执行下一条规则。"""

    @model_validator(mode="after")
    def _check_kind_fields(self) -> "RuleUpsertRequest":
        if self.kind == RuleKind.SCORING and self.weight is None:
            raise ValueError("scoring 规则必须提供 weight")
        if self.kind == RuleKind.DECISION and (
            self.disposition_match is None or self.disposition_miss is None
        ):
            raise ValueError("decision 规则必须提供 dispositionMatch 和 dispositionMiss")
        return self


class RuleRollbackRequest(BaseSchema):
    target_version: int = Field(ge=1)


class RuleGroupUpsertRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=64)
    mode: GroupMode = GroupMode.BLOCKLIST
    priority: RulePriority = RulePriority.NORMAL
    enabled: bool = True
    on_no_match: Disposition | None = Field(default=None, alias="onNoMatch")


class RuleTestRequest(BaseSchema):
    rule: DecisionRule
    sample_context: dict = Field(default_factory=dict)


# ---------- Analytics ----------
class AnalyticsBaseRequest(BaseSchema):
    site_id: int | None = None
    start: datetime
    end: datetime
    filters: dict[str, str] = Field(default_factory=dict)


class TimelineRequest(AnalyticsBaseRequest):
    granularity: Literal["minute", "hour", "day"] = "hour"
    dimension: Literal["disposition", "is_bot", "crawler_category", "crawler_vendor"] = (
        "disposition"
    )
    """分组维度。默认 disposition 保持旧行为；爬虫三维度用于爬虫流量趋势图。"""


class TopEntityRequest(AnalyticsBaseRequest):
    dimension: Literal[
        "ip",
        "device",
        "country",
        "decided_by",
        "mechanism",
        "verdict",
        "is_bot",
        "crawler_category",
        "crawler_vendor",
    ] = "ip"
    limit: int = Field(default=20, ge=1, le=100)


class RuleHitRateRequest(BaseSchema):
    """规则命中率请求。

    不继承 ``AnalyticsBaseRequest``：命中率读日聚合 MV，用不上它的 ``filters``
    （MV 里只有 log_date/site_id/rule_id 三个维度），带上一个静默失效的字段
    比没有更糟。
    """

    site_id: int | None = None
    start: datetime
    end: datetime
    limit: int = Field(default=50, ge=1, le=200)


# ---------- Clock 频控 ----------
class ClockLimitsUpdateRequest(BaseSchema):
    """频控阈值更新请求。

    这里刻意不复用 ``ClockLimits``：它带 ``site_id``，而 site_id 来自路径参数，
    body 里再出现一次就有了两个真相来源，不一致时该信谁没有明确答案。
    窗口名与阈值范围的校验交给 service 层构造 ``ClockLimits`` 时统一执行，
    避免同一套规则在 DTO 和领域对象里写两遍。
    """

    enabled: bool = True
    windows: dict[str, int] = Field(default_factory=dict)
    ban_seconds: int = Field(default=DEFAULT_BAN_SECONDS, alias="banSeconds", ge=0)
    ban_enabled: bool = Field(default=True, alias="banEnabled")


class ClockBanRequest(BaseSchema):
    """手工封禁请求。"""

    dimension: ClockDimension
    value: str = Field(min_length=1, max_length=128)
    seconds: int = Field(default=DEFAULT_BAN_SECONDS, ge=1, le=MAX_BAN_SECONDS)
    reason: str = Field(default="manual", max_length=128)


# ---------- PageResource ----------
from src.domain.page_resource.entities import PageResourceKind  # noqa: E402


class PageResourceCreateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    kind: PageResourceKind = PageResourceKind.SAFE
    content: str = Field(default="")
    content_type: str = Field(
        default="text/html; charset=utf-8", alias="contentType", max_length=64
    )
    enabled: bool = True


class PageResourceUpdateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    kind: PageResourceKind
    content: str
    content_type: str = Field(alias="contentType", max_length=64)
    enabled: bool


class PageResourceDetailResponse(BaseSchema):
    id: int | None
    site_id: int = Field(alias="siteId")
    app_id: int = Field(alias="appId", deprecated=True)
    name: str
    kind: PageResourceKind
    content: str
    content_type: str = Field(alias="contentType")
    enabled: bool
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


# ---------- 封禁批量解除 ----------
class BanTargetSchema(BaseSchema):
    """一个封禁目标。"""

    dimension: ClockDimension
    value: str = Field(min_length=1, max_length=128)


class BanUnbanBatchRequest(BaseSchema):
    """批量解封请求。

    上限 200 条：一次 ``DEL`` 的键数直接决定 Redis 的阻塞时长，无上限时一个
    大 body 就能让网关的频控读写排队。
    """

    items: list[BanTargetSchema] = Field(min_length=1, max_length=200)


# ---------- 白名单 ----------
class WhitelistAddRequest(BaseSchema):
    """新增白名单请求。

    ``created_by`` 不在 body 里——它来自 JWT，让前端自报会让审计信息可伪造。
    """

    dimension: WhitelistDimension
    value: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=256)


# ---------- Scoring 评分配置 ----------
class ScoringConfigSchema(BaseSchema):
    id: int
    site_id: int
    name: str
    enabled: bool
    threshold_suspect: int
    threshold_hostile: int
    weights: dict[str, int]
    disposition_suspect: DecisionDisposition | None = None
    disposition_hostile: DecisionDisposition | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScoringConfigUpsertRequest(BaseSchema):
    """评分配置新建/更新请求（PUT 语义，全量覆盖）。"""

    name: str = Field(default="", max_length=128)
    enabled: bool = True
    threshold_suspect: int = Field(default=40, ge=0, le=100)
    threshold_hostile: int = Field(default=70, ge=0, le=100)
    weights: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "scorer 名 → 整数权重映射，范围 -1000..1000。"
            "gateway 侧接收后除以 10 换算为浮点量纲（与 scorer 类默认权重 1.0 量级对齐），"
            "存储时保留原始整数，不在 admin 侧换算。"
        ),
    )
    disposition_suspect: DecisionDisposition | None = None
    """自定义处置。verdict 不在此填写——由 mechanism 推导，与规则页保持一致。"""
    disposition_hostile: DecisionDisposition | None = None

"""规则 Schema：按种类拆分为打分规则与决策规则。

为什么拆分
----------
旧模型单个 ``Rule`` 同时带 ``weight``（打分语义）和 ``disposition``
（终止语义），而匹配器是首次命中即终止的——终止型规则上的 weight 没有意义，
只想贡献分数的规则又被迫填一个 disposition。两个字段互斥却并存。

拆开后非法组合在**类型层面就构造不出来**，不需要运行时校验，也不需要旧版
``inherit`` 那种 magic value 在运行时再判断一次种类。

``on_no_match`` 的作用域
------------------------
「未命中白名单则拒绝」不是单条规则的属性，而是**规则组**的属性。旧版把
``on_miss`` 挂在每条规则上并全局遍历，导致新增一条无关规则就可能改变全站
默认处置。本模型将其锁定在 :class:`RuleGroup` 内。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from fangyu_shared.rules.operators import OPERATOR_NAMES
from fangyu_shared.schemas.common import BaseSchema
from fangyu_shared.schemas.disposition import DecisionDisposition, Disposition


class RuleStatus(str, Enum):
    DRAFT = "draft"
    SHADOW = "shadow"
    PUBLISHED = "published"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class RulePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RuleKind(str, Enum):
    SCORING = "scoring"
    DECISION = "decision"


class GroupMode(str, Enum):
    """规则组模式，决定 ``on_no_match`` 是否有意义。"""

    BLOCKLIST = "blocklist"
    ALLOWLIST = "allowlist"


_ALLOWED_OPS = OPERATOR_NAMES
"""规则条件允许的操作符白名单，直接取自求值器实现表。

从实现派生而非手写常量，避免出现「白名单放行但求值器未实现」的静默 False。
"""

ALLOWED_CONTEXT_ROOTS: frozenset[str] = frozenset({"device", "ip", "ua", "request", "intel"})
"""条件 field 允许的顶层命名空间，与 ProfileSnapshot.to_evaluation_context() 对应。"""


class RuleCondition(BaseSchema):
    field: str = Field(..., max_length=64)
    op: str = Field(..., max_length=24)
    value: Any

    @field_validator("op")
    @classmethod
    def _check_op(cls, v: str) -> str:
        if v not in _ALLOWED_OPS:
            raise ValueError(f"不支持的规则操作符: {v}")
        return v


class RuleBase(BaseSchema):
    """规则公共字段。

    ``conditions`` 至少一条：旧版 ``if not conditions: return True`` 会让
    配错的空条件规则命中**所有流量**并施加其处置动作。风控系统必须
    fail-closed，因此空条件在校验期直接拒绝。
    """

    id: int | None = None
    app_id: int = Field(default=0, alias="appId", ge=0)
    """站点分片标记。

    规则与站点是多对多关系（关联表 biz_rule_site），规则本身不归属某个站点。
    该字段仅在写入 Redis ``fangyu:rules:{app_id}`` 分片时按目标站点逐一赋值，
    供 gateway 侧沿用既有的按站点读取逻辑；admin 侧查询返回的规则该值为 0。
    """
    site_ids: list[int] = Field(default_factory=list, alias="siteIds")
    """已绑定的站点 id 列表，由 admin 侧填充，gateway 不使用。"""
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    status: RuleStatus = RuleStatus.DRAFT
    priority: RulePriority = RulePriority.NORMAL
    conditions: list[RuleCondition] = Field(..., min_length=1)
    match_all: bool = Field(default=True, alias="matchAll")
    group: str | None = Field(default=None, max_length=64)
    version: int = Field(default=1, ge=1)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    published_at: datetime | None = Field(default=None, alias="publishedAt")

    @field_validator("conditions")
    @classmethod
    def _check_field_roots(cls, v: list[RuleCondition]) -> list[RuleCondition]:
        for cond in v:
            root = cond.field.split(".", 1)[0]
            if root not in ALLOWED_CONTEXT_ROOTS:
                raise ValueError(
                    f"条件 field 顶层命名空间非法: {cond.field}"
                    f"（允许 {sorted(ALLOWED_CONTEXT_ROOTS)}）"
                )
        return v

    @property
    def is_active(self) -> bool:
        """是否参与真实决策。SHADOW 只做影子评估，不影响结果。"""
        return self.status == RuleStatus.PUBLISHED

    @property
    def is_shadow(self) -> bool:
        return self.status == RuleStatus.SHADOW


class ScoringRule(RuleBase):
    """打分规则：贡献权重，永不终止流水线。

    没有 ``disposition`` 字段——打分规则不做处置决策。
    """

    kind: RuleKind = RuleKind.SCORING
    weight: int = Field(default=10, ge=-1000, le=1000)

    @field_validator("kind")
    @classmethod
    def _pin_kind(cls, v: RuleKind) -> RuleKind:
        if v != RuleKind.SCORING:
            raise ValueError("ScoringRule.kind 必须为 scoring")
        return v


class DecisionRule(RuleBase):
    """决策规则：命中即终止流水线并施加处置。

    双路处置（新）：命中走 ``disposition_match``，未命中走 ``disposition_miss``。
    向后兼容（旧）：只传 ``disposition`` 时自动回填 ``disposition_match``，
    ``disposition_miss`` 默认放行。没有 ``weight`` 字段——命中即终止，权重无意义。
    """

    kind: RuleKind = RuleKind.DECISION
    disposition_match: DecisionDisposition | None = None
    disposition_miss: DecisionDisposition | None = None
    # 兼容旧版单路处置（回填/迁移用）；新规则优先用 disposition_match
    # @deprecated: 此字段将在下一个大版本移除，迁移时请改用 disposition_match + disposition_miss
    disposition: Disposition | None = None

    @field_validator("kind")
    @classmethod
    def _pin_kind(cls, v: RuleKind) -> RuleKind:
        if v != RuleKind.DECISION:
            raise ValueError("DecisionRule.kind 必须为 decision")
        return v

    @model_validator(mode="after")
    def _backfill_disposition(self) -> "DecisionRule":
        """兼容旧版单路 ``disposition``：如未提供 disposition_match，从 disposition 推导。

        新代码应直接传 disposition_match；旧测试/旧数据只传 disposition 时不需改动。
        """
        if self.disposition_match is None:
            if self.disposition is None:
                raise ValueError(
                    "DecisionRule 必须提供 disposition_match 或 disposition（兼容旧版）"
                )
            # 将旧版 Disposition → DecisionDisposition（去掉 verdict，保留机制与目标）
            d = self.disposition
            # BaseSchema 不是 frozen，可直接赋值（Pydantic v2 推荐写法）
            self.disposition_match = DecisionDisposition(
                mechanism=d.mechanism,
                target=d.target,
                challengeKind=d.challenge_kind,
                ttlSeconds=d.ttl_seconds,
            )
        return self

    @property
    def effective_match_disposition(self) -> Disposition:
        """命中时实际施加的 Disposition（含 verdict）。统一出口，兼容双路与旧版单路。"""
        assert self.disposition_match is not None  # _backfill_disposition 已保证
        if self.disposition is not None:
            # 旧版：直接返回带 verdict 的原始 disposition
            return self.disposition
        return self.disposition_match.to_disposition()

    @property
    def effective_miss_disposition(self) -> Disposition | None:
        """未命中时施加的 Disposition；None 表示继续流水线（不短路）。"""
        if self.disposition_miss is None:
            return None
        return self.disposition_miss.to_disposition()


class RuleGroup(BaseSchema):
    """规则组：为一批决策规则提供共享作用域与兜底处置。

    ``on_no_match`` 仅在 ``mode=allowlist`` 时有意义，表达「组内白名单
    全部未命中 → 施加此处置」。作用域严格限制在组内。
    """

    id: int | None = None
    app_id: int = Field(..., alias="appId", gt=0)
    name: str = Field(..., min_length=1, max_length=64)
    mode: GroupMode = GroupMode.BLOCKLIST
    priority: RulePriority = RulePriority.NORMAL
    enabled: bool = True
    on_no_match: Disposition | None = Field(default=None, alias="onNoMatch")

    @model_validator(mode="after")
    def _check_mode_semantics(self) -> RuleGroup:
        if self.on_no_match is not None and self.mode != GroupMode.ALLOWLIST:
            raise ValueError("on_no_match 仅在 mode=allowlist 时可用")
        if self.mode == GroupMode.ALLOWLIST and self.on_no_match is None:
            raise ValueError("mode=allowlist 必须提供 on_no_match，否则白名单没有兜底语义")
        return self


class RuleSet(BaseSchema):
    """某个 app 的完整规则集，gateway 一次性加载。"""

    app_id: int = Field(..., alias="appId", gt=0)
    decision_rules: list[DecisionRule] = Field(default_factory=list, alias="decisionRules")
    scoring_rules: list[ScoringRule] = Field(default_factory=list, alias="scoringRules")
    groups: list[RuleGroup] = Field(default_factory=list)
    default_disposition: Disposition | None = Field(default=None, alias="defaultDisposition")

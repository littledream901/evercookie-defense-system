"""决策请求/响应契约。

处置模型见 :mod:`fangyu_shared.schemas.disposition`。本模块只负责
gateway 对外的请求/响应形状。

接入来源（IngressKind）
-----------------------
决策请求有两条入口，信号丰富度差异很大：

- ``SDK``：浏览器内 JS 采集，有真实指纹与行为时序。
- ``ADAPTER``：站点服务端（如 PHP）转发，决策发生在页面渲染**之前**，
  此刻没有任何 JS 执行过，**结构上不可能有指纹**。

旧版用 ``AccessSource`` 枚举区分过这两条路径，V2 重写时丢了，导致
``fingerprint`` 被定义成无条件必填——Adapter 路径连请求都发不进来。这里恢复
该维度，并把指纹改为按来源条件必填。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, IPvAnyAddress, model_validator

from fangyu_shared.clock.windows import MAX_BEHAVIOR_EVENTS_PER_REQUEST
from fangyu_shared.schemas.clock import BehaviorEvent
from fangyu_shared.schemas.common import BaseSchema
from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    Mechanism,
    TargetKind,
    Verdict,
)
from fangyu_shared.utils.crypto import sha256_hex


class IngressKind(str, Enum):
    """决策请求的接入来源。"""

    SDK = "sdk"
    ADAPTER = "adapter"


class DecisionContext(BaseSchema):
    """决策上下文，由 SDK 或 Adapter 提交给 gateway。

    ``fingerprint``
        SDK 路径必填；Adapter 路径可省略，由 :meth:`_derive_fingerprint`
        从 ip + user_agent + app_id 派生代理指纹。派生指纹的区分度远低于
        真指纹（同一 NAT 出口下的同型设备会碰撞），所以
        ``fingerprint_is_derived`` 会显式标记，规则侧可据此调整信任度。
    """

    app_id: int = Field(..., alias="appId", gt=0)
    ingress: IngressKind = IngressKind.SDK
    fingerprint: str = Field(default="", max_length=128)
    fingerprint_is_derived: bool = Field(default=False, alias="fingerprintIsDerived")
    device_id: str | None = Field(default=None, alias="deviceId", max_length=128)
    ip: IPvAnyAddress
    user_agent: str = Field(..., alias="userAgent", max_length=1024)
    referer: str | None = Field(default=None, max_length=2048)
    visit_url: str | None = Field(default=None, alias="visitUrl", max_length=2048)
    path: str = Field(default="/", max_length=1024)
    method: str = Field(default="GET", max_length=16)
    session_id: str | None = Field(default=None, alias="sessionId", max_length=128)
    client_language: str | None = Field(default=None, alias="clientLanguage", max_length=64)
    repeat_key: str | None = Field(default=None, alias="repeatKey", max_length=128)
    repeat_value: str | None = Field(default=None, alias="repeatValue", max_length=256)
    evercookie_restored: bool = Field(default=False, alias="evercookieRestored")
    behavior_events: list[BehaviorEvent] = Field(
        default_factory=list,
        alias="behaviorEvents",
        max_length=MAX_BEHAVIOR_EVENTS_PER_REQUEST,
    )
    """本次请求携带的行为事件。仅 SDK 路径会有；Adapter 路径恒为空。

    当前只落时序库供后续分析，**不参与打分**。刻意不建占位打分阶段——旧版
    那个恒为 0 分的 behavior stage 让前端「AI 得分」长期显示 0，是负资产。
    """
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _resolve_fingerprint(self) -> DecisionContext:
        """按来源校验并补全指纹。"""
        if self.fingerprint:
            return self
        if self.ingress == IngressKind.SDK:
            raise ValueError("ingress=sdk 必须提供 fingerprint")
        # Adapter 路径：派生代理指纹并打标
        object.__setattr__(self, "fingerprint", self._derive_fingerprint())
        object.__setattr__(self, "fingerprint_is_derived", True)
        return self

    def _derive_fingerprint(self) -> str:
        """从服务端可见信号派生代理指纹。

        带 ``adapter:`` 前缀是为了让派生指纹在存储与日志里一眼可辨，
        不会与真指纹混淆统计。
        """
        seed = f"{self.app_id}|{self.ip}|{self.user_agent}"
        return f"adapter:{sha256_hex(seed)[:32]}"


class DecisionRequest(BaseSchema):
    """/v2/decide 请求体。"""

    context: DecisionContext
    require_details: bool = Field(default=False, alias="requireDetails")


class DecisionDetail(BaseSchema):
    stage: str
    rule_id: int | None = Field(default=None, alias="ruleId")
    score: float | None = None
    reason: str | None = None


class ShadowOutcome(BaseSchema):
    """影子规则评估结果：命中但不影响真实决策。

    用于发布前用真实流量测算规则影响面，消除盲发布风险。
    """

    rule_id: int | None = Field(default=None, alias="ruleId")
    rule_name: str = Field(default="", alias="ruleName")
    verdict: Verdict
    mechanism: Mechanism


class DecisionResponse(BaseSchema):
    """/v2/decide 响应。

    ``target_url`` 已按当次请求渲染完成（占位符已替换）。渲染发生在缓存
    读取**之后**，因此同一访客访问不同 URL 不会串味。
    """

    verdict: Verdict
    mechanism: Mechanism
    target_kind: TargetKind = Field(default=TargetKind.ORIGIN, alias="targetKind")
    target_url: str | None = Field(default=None, alias="targetUrl")
    http_status: int = Field(default=200, alias="httpStatus", ge=100, le=599)
    challenge_kind: ChallengeKind | None = Field(default=None, alias="challengeKind")
    challenge_token: str | None = Field(default=None, alias="challengeToken")
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    rule_ids: list[int] = Field(default_factory=list, alias="ruleIds")
    reason: str | None = None
    decided_by: str = Field(default="default", alias="decidedBy")
    decided_stage: str = Field(default="default", alias="decidedStage")
    ttl_seconds: int = Field(default=300, alias="ttlSeconds", ge=0)
    details: list[DecisionDetail] = Field(default_factory=list)
    shadow: list[ShadowOutcome] = Field(default_factory=list)
    request_id: str | None = Field(default=None, alias="requestId")

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
from urllib.parse import urlparse

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
        从 ip + user_agent + site_id 派生代理指纹。派生指纹的区分度远低于
        真指纹（同一 NAT 出口下的同型设备会碰撞），所以
        ``fingerprint_is_derived`` 会显式标记，规则侧可据此调整信任度。
    """

    site_id: int = Field(default=0, alias="siteId", ge=0)
    """站点ID，由 gateway 根据 API Key 覆写，适配器无需填写。"""
    ingress: IngressKind = IngressKind.SDK
    fingerprint: str = Field(default="", max_length=128)
    fingerprint_is_derived: bool = Field(default=False, alias="fingerprintIsDerived")
    device_id: str | None = Field(default=None, alias="deviceId", max_length=128)
    ip: IPvAnyAddress | None = None
    """访客 IP。

    SDK 路径可省略——浏览器**无法得知自己的出口 IP**，只能由 gateway 从
    socket peer 填充（见 ``v2/decide.py`` 的 ``_resolve_context_ip``）。即使
    客户端传了值也会被服务端覆盖，所以这里不做必填校验。

    Adapter 路径必填：决策发生在站点服务端，那里才知道真实来源 IP，且
    gateway 看到的 socket peer 是站点服务器而非访客。
    """
    user_agent: str = Field(..., alias="userAgent", max_length=1024)
    referer: str | None = Field(default=None, max_length=2048)
    visit_url: str | None = Field(default=None, alias="visitUrl", max_length=2048)
    path: str = Field(default="/", max_length=1024)
    method: str = Field(default="GET", max_length=16)
    session_id: str | None = Field(default=None, alias="sessionId", max_length=128)
    client_language: str | None = Field(default=None, alias="clientLanguage", max_length=256)
    """语言偏好。SDK 送 ``navigator.language`` 单值，网关缺省时回填整个
    ``Accept-Language`` 头（``zh-CN,zh;q=0.9,en;q=0.8``），故长度按头部放宽。"""
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
    def _derive_path_from_visit_url(self) -> DecisionContext:
        """``path`` 缺省时从 ``visit_url`` 解析补齐。

        存在原因：三个服务端适配器（nginx-lua / CF Worker / WordPress）历史上
        只上报 ``visitUrl``，不上报 ``path``。而 ``path`` 的默认值是 ``"/"``，
        规则引擎的 ``request.path`` 直接取该字段，不做任何派生。后果有两层：

        - 正向条件永不命中：内置模板「敏感路径阻断」（critical 优先级，
          ``regex ^/(admin|checkout)(/|$)``）对适配器流量完全失效；
        - 否定条件误命中：「路径不在白名单则拦截」会因取值恒为 ``"/"``
          而拦下全部适配器流量。

        兜底放在 schema 而非各适配器，是为了让已部署的存量适配器无需升级即可
        恢复正确行为；适配器侧也已同步补上显式上报，两者一致。

        只在 ``path`` 仍为默认值时派生，绝不覆盖显式上报值——否则 SDK 明确传来的
        ``location.pathname`` 会被 ``visitUrl`` 的解析结果顶掉。
        """
        if self.path == "/" and self.visit_url:
            parsed = urlparse(self.visit_url)
            if parsed.path:
                object.__setattr__(self, "path", parsed.path[:1024])
        return self

    @model_validator(mode="after")
    def _resolve_fingerprint(self) -> DecisionContext:
        """按来源校验并补全指纹。

        Adapter 路径的派生指纹依赖 ``ip``，因此顺带在此校验 Adapter 必须带 IP。
        """
        if self.ingress == IngressKind.ADAPTER and self.ip is None:
            raise ValueError("ingress=adapter 必须提供 ip")

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
        seed = f"{self.site_id}|{self.ip}|{self.user_agent}"
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
    page_content: str | None = Field(default=None, alias="pageContent")
    """serve_alt 命中时由 gateway 填充的页面内容，客户端直接渲染。None 表示非 serve_alt 命中。"""
    page_content_type: str | None = Field(default=None, alias="pageContentType")
    """page_content 的 MIME 类型，适配器据此设置 Content-Type 响应头。

    与 page_content 同时填充。非 HTML 资源（如 JSON 占位）若一律按 HTML 投放会渲染错乱，
    所以内容类型必须随内容一起下发而不能由客户端猜测。
    """
    challenge_token: str | None = Field(default=None, alias="challengeToken")
    """mechanism=challenge 时由 gateway 签发的 HMAC 凭据，客户端完成挑战后携带此 token 提交答案。

    Token 格式：base64(payload) + "." + hmac_sha256(app_secret, payload_base64)
    Payload 包含 {siteId, fingerprint, kind, exp, nonce}，防跨租户盗用、重放攻击、过期使用。
    """

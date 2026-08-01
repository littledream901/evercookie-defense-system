"""处置契约：裁决 / 机制 / 目标 三层正交模型。

设计要点
--------
旧版把「严重级别 × 执行机制」压成一维枚举（ALLOW / ALLOW_LOG /
CHALLENGE_CAPTCHA / BLOCK_HARD ...），每新增一种执行手段都会引发组合爆炸。
本模块改为三个互相独立的维度：

``Verdict``
    裁决——回答「为什么」。纯风险判断，不涉及执行手段。
``Mechanism``
    机制——回答「怎么做」。纯执行手段，不涉及目标地址。
``Target``
    目标——回答「去哪」。承载 URL 与 HTTP 状态码。

三者独立演进：新增机制不影响裁决枚举，新增目标类型不影响机制枚举。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from fangyu_shared.schemas.common import BaseSchema


class Verdict(str, Enum):
    """裁决：风险判断结论。

    对应旧版三桶（money_page / safe_page / high_risk），但命名明确表达
    「这是裁决」而非「这是目的地」——旧版 money_page 听起来像地址，
    实际是裁决，是长期的理解负担。
    """

    TRUSTED = "trusted"
    SUSPECT = "suspect"
    HOSTILE = "hostile"


class Mechanism(str, Enum):
    """机制：执行手段。"""

    PASS = "pass"
    SERVE_ALT = "serve_alt"
    REDIRECT = "redirect"
    CHALLENGE = "challenge"
    DENY = "deny"
    NOT_FOUND = "not_found"


class TargetKind(str, Enum):
    """目标类型。"""

    ORIGIN = "origin"
    URL = "url"
    PAGE_RESOURCE = "page_resource"
    STATUS_ONLY = "status_only"


class ChallengeKind(str, Enum):
    """挑战类型，仅 Mechanism.CHALLENGE 时有意义。"""

    CAPTCHA = "captcha"
    JS = "js"


_MECHANISM_STATUS: dict[Mechanism, int] = {
    Mechanism.PASS: 200,
    Mechanism.SERVE_ALT: 200,
    Mechanism.REDIRECT: 302,
    Mechanism.CHALLENGE: 403,
    Mechanism.DENY: 403,
    Mechanism.NOT_FOUND: 404,
}
"""机制 → 默认 HTTP 状态码。Target.http_status 未显式指定时由此推导。"""


class Target(BaseSchema):
    """处置目标：去哪。

    ``url`` 支持占位符，由 gateway 响应层按请求上下文渲染（见
    ``render_target``）。**不要在缓存前渲染**——决策缓存按
    (app_id, fingerprint, ip) 命中，同一访客访问不同 URL 会复用同一条
    缓存，提前渲染会导致跳转地址串味。
    """

    kind: TargetKind = TargetKind.ORIGIN
    url: str | None = Field(default=None, max_length=1024)
    http_status: int | None = Field(default=None, alias="httpStatus", ge=100, le=599)

    @model_validator(mode="after")
    def _check_url_required(self) -> Target:
        if self.kind in (TargetKind.URL, TargetKind.PAGE_RESOURCE) and not self.url:
            raise ValueError(f"target.kind={self.kind.value} 必须提供 url")
        return self


class Disposition(BaseSchema):
    """完整处置决策：裁决 + 机制 + 目标。

    ``ttl_seconds``
        决策缓存时长。旧版没有缓存，每次请求全量走流水线；V2 保留缓存，
        因此 TTL 是处置的一部分。
    """

    verdict: Verdict
    mechanism: Mechanism
    target: Target = Field(default_factory=Target)
    challenge_kind: ChallengeKind | None = Field(default=None, alias="challengeKind")
    ttl_seconds: int = Field(default=300, alias="ttlSeconds", ge=0, le=86400)

    @model_validator(mode="after")
    def _check_semantics(self) -> Disposition:
        if self.mechanism == Mechanism.REDIRECT and not self.target.url:
            raise ValueError("mechanism=redirect 必须提供 target.url")
        if self.mechanism == Mechanism.CHALLENGE and self.challenge_kind is None:
            raise ValueError("mechanism=challenge 必须提供 challenge_kind")
        if self.mechanism != Mechanism.CHALLENGE and self.challenge_kind is not None:
            raise ValueError("challenge_kind 仅在 mechanism=challenge 时可用")
        return self

    @property
    def effective_status(self) -> int:
        """最终 HTTP 状态码：显式指定优先，否则按机制推导。"""
        if self.target.http_status is not None:
            return self.target.http_status
        return _MECHANISM_STATUS.get(self.mechanism, 200)

    @property
    def is_terminal(self) -> bool:
        """是否阻断了原始请求（用于报表口径与指标打点）。"""
        return self.mechanism in (
            Mechanism.DENY,
            Mechanism.NOT_FOUND,
            Mechanism.CHALLENGE,
        )


# ── 常用预设 ──
# 三层模型表达力强但书写啰嗦，常用组合给出工厂函数，避免各处重复构造。

def allow(*, ttl_seconds: int = 600) -> Disposition:
    return Disposition(verdict=Verdict.TRUSTED, mechanism=Mechanism.PASS, ttlSeconds=ttl_seconds)


def observe(*, ttl_seconds: int = 300) -> Disposition:
    """放行但缩短缓存，用于「仅观察」场景（旧版 ALLOW_LOG）。"""
    return Disposition(verdict=Verdict.SUSPECT, mechanism=Mechanism.PASS, ttlSeconds=ttl_seconds)


def challenge(
    kind: ChallengeKind = ChallengeKind.CAPTCHA, *, ttl_seconds: int = 300
) -> Disposition:
    return Disposition(
        verdict=Verdict.SUSPECT,
        mechanism=Mechanism.CHALLENGE,
        challengeKind=kind,
        ttlSeconds=ttl_seconds,
    )


def deny(*, ttl_seconds: int = 900) -> Disposition:
    return Disposition(verdict=Verdict.HOSTILE, mechanism=Mechanism.DENY, ttlSeconds=ttl_seconds)


def not_found(*, ttl_seconds: int = 900) -> Disposition:
    """静默阻断：返回 404 假装资源不存在（旧版 BLOCK_SILENT）。"""
    return Disposition(
        verdict=Verdict.HOSTILE, mechanism=Mechanism.NOT_FOUND, ttlSeconds=ttl_seconds
    )


def redirect(url: str, *, permanent: bool = False, ttl_seconds: int = 300) -> Disposition:
    return Disposition(
        verdict=Verdict.SUSPECT,
        mechanism=Mechanism.REDIRECT,
        target=Target(kind=TargetKind.URL, url=url, httpStatus=301 if permanent else 302),
        ttlSeconds=ttl_seconds,
    )


def serve_alt(page: str, *, ttl_seconds: int = 300) -> Disposition:
    """投放替代内容（旧版 safe_page + static_page）。"""
    return Disposition(
        verdict=Verdict.SUSPECT,
        mechanism=Mechanism.SERVE_ALT,
        target=Target(kind=TargetKind.PAGE_RESOURCE, url=page),
        ttlSeconds=ttl_seconds,
    )


DEFAULT_DISPOSITION_TTL = 300
"""无法解析出处置时的兜底 TTL。"""

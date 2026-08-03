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
    URL_POOL = "url_pool"
    PAGE_RESOURCE = "page_resource"
    STATUS_ONLY = "status_only"


class ChallengeKind(str, Enum):
    """挑战类型，仅 Mechanism.CHALLENGE 时有意义。"""

    CAPTCHA = "captcha"
    JS = "js"


class RotationStrategy(str, Enum):
    """轮询选址策略。
    
    HASH
        无状态哈希取模（默认）。按 request_id 做 blake2b，近似均匀分布。
        不是真轮转——短时间内可能倾斜，流量大时收敛到均匀。
    WEIGHTED
        按权重分配（灰度放量、主备分流）。无状态，用 hash 落权重区间。
    STICKY
        访客粘性（A/B 实验分组）。seed 换成 fingerprint，同一访客固定地址。
        **牺牲分摊性**——池子退化成按访客分片，须在 UI 明确提示。
    ROUND_ROBIN
        严格轮转。需 Redis 计数器维持状态，决策链路多一次写操作。
    FAILOVER
        主备容灾。健康检查可用时按顺序 failover，否则永远第一个。
    """

    HASH = "hash"
    WEIGHTED = "weighted"
    STICKY = "sticky"
    ROUND_ROBIN = "round_robin"
    FAILOVER = "failover"


class PoolEntry(BaseSchema):
    """地址池条目。"""

    url: str = Field(max_length=1024)
    weight: int = Field(default=1, ge=0, le=100)
    """权重（仅 WEIGHTED 策略生效）。0 表示临时禁用。"""
    enabled: bool = True
    """是否启用。false 时选址跳过（手动摘除）。"""
    daily_quota: int | None = Field(default=None, alias="dailyQuota", ge=1)
    """每日配额上限。None 表示不限。打满后自动从池中摘除至次日零点。"""
    hourly_quota: int | None = Field(default=None, alias="hourlyQuota", ge=1)
    """每小时配额上限。None 表示不限。打满后自动从池中摘除至整点。"""


class Rotation(BaseSchema):
    """轮询配置。仅 TargetKind.URL_POOL 时有意义。"""

    strategy: RotationStrategy = RotationStrategy.HASH
    entries: list[PoolEntry] = Field(default_factory=list, max_length=32)
    """地址池条目。上限 32（与旧版 urls 字段一致）。"""

    @model_validator(mode="after")
    def _check_entries(self) -> "Rotation":
        if not self.entries:
            raise ValueError("rotation.entries 不能为空")
        enabled_count = sum(1 for e in self.entries if e.enabled and e.weight > 0)
        if enabled_count == 0:
            raise ValueError("rotation.entries 至少需要一个 enabled=True 且 weight>0 的条目")
        return self


_MECHANISM_STATUS: dict[Mechanism, int] = {
    Mechanism.PASS: 200,
    Mechanism.SERVE_ALT: 200,
    Mechanism.REDIRECT: 302,
    Mechanism.CHALLENGE: 403,
    Mechanism.DENY: 403,
    Mechanism.NOT_FOUND: 404,
}
"""机制 → 默认 HTTP 状态码。Target.http_status 未显式指定时由此推导。"""


def resolve_http_status(mechanism: Mechanism, target: Target) -> int:
    """按给定机制解析最终 HTTP 状态码：显式指定优先，否则按机制推导。

    独立成函数是因为调用方有时需要按**降级后**的机制重算状态码（例如
    redirect 渲染失败降级为 pass 时），而不是取原始 disposition.mechanism。
    """
    if target.http_status is not None:
        return target.http_status
    return _MECHANISM_STATUS.get(mechanism, 200)


_MECHANISM_TARGET_KINDS: dict[Mechanism, frozenset[TargetKind]] = {
    Mechanism.PASS: frozenset({TargetKind.ORIGIN}),
    Mechanism.SERVE_ALT: frozenset({TargetKind.PAGE_RESOURCE}),
    Mechanism.REDIRECT: frozenset({TargetKind.URL, TargetKind.URL_POOL}),
    Mechanism.CHALLENGE: frozenset({TargetKind.ORIGIN}),
    Mechanism.DENY: frozenset({TargetKind.ORIGIN, TargetKind.STATUS_ONLY}),
    Mechanism.NOT_FOUND: frozenset({TargetKind.ORIGIN, TargetKind.STATUS_ONLY}),
}
"""机制 → 合法目标类型白名单。

三层模型正交只是说三个维度**各自**独立演进，不代表任意组合都有意义：
``deny + kind=url`` 里的 url 永不会被使用，``serve_alt + kind=origin`` 则
拿不到要投放的资源名。这类组合不会报错，只会静默地不按预期工作，比直接
拒绝更难排查，因此在契约层就拦掉。

与 dashboard-ui 的 ``MECHANISM_TARGET_KINDS`` 保持一致：前端据此收窄下拉选项，
后端据此兜住绕过 UI 的直接调用。
"""


def _check_target_kind(mechanism: Mechanism, target: Target) -> None:
    """校验机制与目标类型的组合合法性。两个 Disposition 类共用。"""
    allowed = _MECHANISM_TARGET_KINDS.get(mechanism)
    if allowed is not None and target.kind not in allowed:
        expected = "、".join(sorted(k.value for k in allowed))
        raise ValueError(
            f"mechanism={mechanism.value} 不支持 target.kind={target.kind.value}，"
            f"仅允许 {expected}"
        )


class Target(BaseSchema):
    """处置目标：去哪。

    ``url`` 支持占位符，由 gateway 响应层按请求上下文渲染（见
    ``render_target``）。**不要在缓存前渲染**——决策缓存按
    (app_id, fingerprint, ip) 命中，同一访客访问不同 URL 会复用同一条
    缓存，提前渲染会导致跳转地址串味。
    """

    kind: TargetKind = TargetKind.ORIGIN
    url: str | None = Field(default=None, max_length=1024)
    urls: list[str] | None = Field(default=None, max_length=32)
    """轮询地址池（对应旧版 JUMP_MODE=2 的多地址轮询）。

    **已废弃**：保留仅为向后兼容。新配置应使用 ``kind=URL_POOL + rotation``。
    与 ``url`` 的关系：``urls`` 非空时 ``url`` 被忽略，网关按请求轮询选一个。
    上限 32 是防御性的——地址池是运维手填的配置，没有上限时一次误粘贴
    就能让规则体积失控，而规则整体会进 Redis 并在每次决策时反序列化。

    **选路发生在网关侧**，响应只回选中的单个 ``target_url``，不下发整个池子：
    池子是站点的兜底落地页清单，下发等于让任何能调 ``/v2/decide`` 的人一次
    拿全所有备用地址。同时也避免 PHP / Lua / Worker / 浏览器四份适配器各自
    实现一遍取模逻辑——四份实现就是四次分叉机会。
    """
    rotation: Rotation | None = None
    """轮询配置（仅 kind=URL_POOL 时有意义）。新模型，替代旧版 urls 字段。"""
    http_status: int | None = Field(default=None, alias="httpStatus", ge=100, le=599)

    @model_validator(mode="after")
    def _check_url_required(self) -> Target:
        if self.urls is not None:
            cleaned = [u for u in self.urls if isinstance(u, str) and u.strip()]
            if not cleaned:
                raise ValueError("target.urls 不能是空列表——要么给地址，要么置 None")
        
        # URL_POOL 必须提供 rotation
        if self.kind == TargetKind.URL_POOL and self.rotation is None:
            raise ValueError("target.kind=url_pool 必须提供 rotation 配置")
        
        # 非 URL_POOL 不能有 rotation
        if self.kind != TargetKind.URL_POOL and self.rotation is not None:
            raise ValueError("rotation 仅在 target.kind=url_pool 时可用")
        
        # URL 和 PAGE_RESOURCE 必须有地址（兼容旧版 urls 或新版 rotation）
        if self.kind == TargetKind.URL and not self.url_pool:
            raise ValueError("target.kind=url 必须提供 url 或 urls")
        if self.kind == TargetKind.PAGE_RESOURCE and not self.url_pool:
            raise ValueError("target.kind=page_resource 必须提供 url 或 urls")
        
        return self

    @property
    def url_pool(self) -> tuple[str, ...]:
        """候选地址池。``urls`` 优先，否则退化为单元素的 ``url``。

        统一出口，免得调用方到处写 ``target.urls or [target.url]`` 还得处理
        ``url`` 为 None 的分支。
        
        **已废弃**：仅为向后兼容保留。新代码应使用 ``rotation_pool``。
        """
        if self.urls:
            return tuple(u for u in self.urls if isinstance(u, str) and u.strip())
        if self.url:
            return (self.url,)
        return ()

    @property
    def rotation_pool(self) -> tuple[str, ...]:
        """轮询地址池（新模型）。优先级：rotation.entries > urls > url。
        
        统一获取地址池的接口，屏蔽新旧模型差异。
        """
        # 新模型：从 rotation.entries 提取
        if self.rotation and self.rotation.entries:
            return tuple(e.url for e in self.rotation.entries if e.url.strip())
        # 旧模型兼容：urls 或 url
        return self.url_pool


class DecisionDisposition(BaseSchema):
    """规则处置动作：机制 + 目标，不含 verdict。

    用于规则的命中/未命中双路处置，verdict 由规则引擎根据 mechanism 推导，
    不需要前端/运维在每条规则里重复填写。
    """

    mechanism: Mechanism
    target: Target = Field(default_factory=Target)
    challenge_kind: ChallengeKind | None = Field(default=None, alias="challengeKind")
    ttl_seconds: int = Field(default=300, alias="ttlSeconds", ge=0, le=86400)

    @model_validator(mode="after")
    def _check_semantics(self) -> "DecisionDisposition":
        _check_target_kind(self.mechanism, self.target)
        if self.mechanism == Mechanism.REDIRECT and not self.target.rotation_pool:
            raise ValueError("mechanism=redirect 必须提供 target.url、target.urls 或 target.rotation")
        if self.mechanism == Mechanism.CHALLENGE and self.challenge_kind is None:
            raise ValueError("mechanism=challenge 必须提供 challenge_kind")
        if self.mechanism != Mechanism.CHALLENGE and self.challenge_kind is not None:
            raise ValueError("challenge_kind 仅在 mechanism=challenge 时可用")
        return self

    def to_disposition(self, verdict: "Verdict | None" = None) -> "Disposition":
        """转换为含 verdict 的完整 Disposition，verdict 可由外部指定或按机制推导。"""
        _MECHANISM_VERDICT: dict[Mechanism, Verdict] = {
            Mechanism.PASS: Verdict.TRUSTED,
            Mechanism.SERVE_ALT: Verdict.SUSPECT,
            Mechanism.REDIRECT: Verdict.SUSPECT,
            Mechanism.CHALLENGE: Verdict.SUSPECT,
            Mechanism.DENY: Verdict.HOSTILE,
            Mechanism.NOT_FOUND: Verdict.HOSTILE,
        }
        resolved = verdict or _MECHANISM_VERDICT.get(self.mechanism, Verdict.SUSPECT)
        return Disposition(
            verdict=resolved,
            mechanism=self.mechanism,
            target=self.target,
            challengeKind=self.challenge_kind,
            ttlSeconds=self.ttl_seconds,
        )


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
        _check_target_kind(self.mechanism, self.target)
        if self.mechanism == Mechanism.REDIRECT and not self.target.url_pool:
            raise ValueError("mechanism=redirect 必须提供 target.url 或 target.urls")
        if self.mechanism == Mechanism.CHALLENGE and self.challenge_kind is None:
            raise ValueError("mechanism=challenge 必须提供 challenge_kind")
        if self.mechanism != Mechanism.CHALLENGE and self.challenge_kind is not None:
            raise ValueError("challenge_kind 仅在 mechanism=challenge 时可用")
        return self

    @property
    def effective_status(self) -> int:
        """最终 HTTP 状态码：显式指定优先，否则按机制推导。"""
        return resolve_http_status(self.mechanism, self.target)

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


def redirect(
    url: str | list[str], *, permanent: bool = False, ttl_seconds: int = 300
) -> Disposition:
    """跳转。传 list 即启用轮询地址池。

    ``permanent=True`` 与轮询是矛盾组合：301 会被浏览器与中间代理长期缓存，
    第一次选中的地址会被钉死，后续轮询完全失效。因此地址池强制 302。
    """
    pool = [url] if isinstance(url, str) else list(url)
    single = len(pool) == 1
    return Disposition(
        verdict=Verdict.SUSPECT,
        mechanism=Mechanism.REDIRECT,
        target=Target(
            kind=TargetKind.URL,
            url=pool[0] if single else None,
            urls=None if single else pool,
            httpStatus=301 if (permanent and single) else 302,
        ),
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

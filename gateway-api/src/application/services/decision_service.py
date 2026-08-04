"""决策服务：编排决策流水线。

流水线阶段（命中即返回，跳过后续）
1. WHITELIST      - app 级 IP/指纹白名单，命中直接放行（**最前**，见下）
2. CLOCK          - 频控计数 + 封禁检查（**前置于缓存**，见下）
3. CACHE          - 命中即返回未渲染决策，渲染后响应
4. PROFILE        - 构建设备/IP 画像上下文
5. DECISION_RULE  - 决策规则匹配 + allowlist 组兜底
6. THREAT_INTEL   - IP 威胁情报
7. SECURITY       - 基础安全检查（黑名单/地理围栏/Tor）
8. RISK_SCORING   - 风险评分聚合
9. DEFAULT        - app 级默认 → 系统默认

为什么白名单排在 Clock 之前
---------------------------
白名单是误封的兜底通道。计划里写的是「在 SecurityChecker 之前」，但只挡在
SecurityChecker 前面不够用：真正把人误伤到需要人工干预的，恰恰是排在更前面
的频控封禁与威胁情报——被封禁的访客连 SecurityChecker 都到不了。放在最前面
才能保证「加进白名单就一定能访问」这个运维直觉成立。

代价是白名单流量不再被频控计数。这是有意的：既然已经声明这条流量不参与
风控，给它累积计数只会在移出白名单的瞬间造成一次立即封禁。

为什么 Clock 必须前置于缓存
---------------------------
频控依赖「每个请求都被计数」。若放在缓存之后，缓存命中的请求就不计数了，
突发流量会被严重漏计——而突发正是频控要拦的东西。因此 Clock 无条件先执行，
超限直接终止，不查缓存。

反向约束：频控结论**不能写入决策缓存**。它与时间强相关，缓存后访客在窗口
滑过之后仍会被拒。由 ``DecisionOutcome.is_cacheable`` 把这个判断收口。

渲染时机
--------
``target_url`` 的占位符渲染发生在 :meth:`_render`，即**缓存之后**。
缓存 key 不含 URL，提前渲染会导致同一访客不同页面复用同一跳转地址。

事件发布不在关键路径上
--------------------
决策事件通过 :meth:`DecisionService._schedule_event` 交给后台任务发布，响应
不等待 Redis XADD 完成。此前是 inline ``await``，等于把 Redis 的 P99 加进
每一次决策的 P99——事件只供离线分析，没有任何理由让它决定同步决策的延迟。

代价是进程被强杀时在飞的事件会丢。用 :meth:`drain_events` 在 lifespan 关闭
阶段等待排空把这个窗口收敛到「正常关闭时不丢」。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any

from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.challenge_token import issue_challenge_token, DEFAULT_TTL as DEFAULT_CHALLENGE_TTL
from fangyu_shared.logging import get_logger
from fangyu_shared.metrics import (
    decision_cache_hits_total,
    decision_latency_seconds,
    decision_requests_total,
)
from fangyu_shared.schemas.decision import (
    DecisionContext,
    DecisionDetail,
    DecisionRequest,
    DecisionResponse,
    ShadowOutcome,
)
from fangyu_shared.schemas.disposition import (
    Disposition,
    Mechanism,
    TargetKind,
    Verdict,
    allow,
    challenge,
    deny,
    not_found,
    resolve_http_status,
)
from fangyu_shared.schemas.event import ConditionTraceEvent, DecisionEvent
from fangyu_shared.schemas.target_render import pick_target, render_pool, resolve_rotation_order
from fangyu_shared.utils.crypto import sha256_hex
from fangyu_shared.utils.time import utcnow_ms

from src.domain.clock.guard import ClockGuard, ClockVerdict
from src.domain.decision.disposition import DecidedBy, DispositionResolver, ResolvedDisposition
from src.domain.decision.entities import (
    DecisionOutcome,
    PipelineStage,
    PipelineStageResult,
    ShadowHit,
)
from src.domain.profile.builder import ProfileBuilder, ProfileSnapshot
from src.domain.risk.pipeline import RiskPipeline
from src.domain.risk.security import SecurityChecker
from src.domain.rule.matcher import DecisionRuleMatcher
from src.domain.rule.tracer import collect_condition_traces, should_trace
from src.infrastructure.cache.decision_cache import (
    CachedDecision,
    CachedShadowHit,
    DecisionCache,
)
from src.infrastructure.cache.page_resource_cache import PageResourceCache
from src.infrastructure.cache.profile_cache import ProfileCache
from src.infrastructure.cache.scoring_config_cache import ScoringConfigCache
from src.infrastructure.cache.server_session_cache import ServerSessionCache
from src.infrastructure.clock.repository import ClockReading, ClockRepository
from src.infrastructure.event_publisher.stream_publisher import StreamEventPublisher
from src.infrastructure.intel import IntelReader
from src.infrastructure.mmdb.reader import MMDBReader
from src.infrastructure.rule_repo.rule_repository import RuleRepository
from src.infrastructure.threat_intel.reader import ThreatIntelReader
from src.infrastructure.whitelist.reader import WhitelistReader

_logger = get_logger("gateway.decision_service")


@dataclass
class DecisionServiceDeps:
    decision_cache: DecisionCache
    profile_cache: ProfileCache
    rule_repository: RuleRepository
    profile_builder: ProfileBuilder
    rule_matcher: DecisionRuleMatcher
    security_checker: SecurityChecker
    risk_pipeline: RiskPipeline
    event_publisher: StreamEventPublisher
    mmdb_reader: MMDBReader
    clock_repository: ClockRepository | None = None
    """None 表示关闭 Clock 阶段。频控是可选能力，缺失时流水线从 CACHE 开始。"""
    clock_guard: ClockGuard | None = None
    page_resource_cache: PageResourceCache | None = None
    """None 表示未配置页面资源缓存；serve_alt 命中时 page_content 将为 None。"""
    whitelist_reader: WhitelistReader | None = None
    """None 表示关闭白名单阶段，流水线从 CLOCK 开始。"""
    intel_reader: IntelReader | None = None
    """None 表示关闭六类维度情报富化，画像的 intel.* 命名空间留空。"""
    scoring_config_cache: ScoringConfigCache | None = None
    """None 表示关闭动态评分配置，阈值由 GatewaySettings 静态值决定。"""
    server_session_cache: ServerSessionCache | None = None
    """None 表示关闭 Hybrid 双层架构的 serverToken 关联。非 None 时：
    - ingress=adapter 且 mechanism=pass 时，把第一层预判存入 Redis
    - ingress=sdk 且 extra.serverToken 存在时，查 Redis 并短路流水线（已拦截则直接返回）
      或把第一层信号注入 context.extra 供评分阶段参考。
    """
    app_key_resolver: Any = None
    """AppKeyResolver，懒导入避免循环依赖。"""
    challenge_pass_store: Any = None
    """ChallengePassStore，用于检查访客是否已通过挑战。"""
    rotation_counter: Any = None
    """RotationCounter，用于 ROUND_ROBIN 策略的单调计数器。"""
    pool_health_store: Any = None
    """PoolHealthStore，用于 FAILOVER 策略的健康检查。"""
    pool_quota_store: Any = None
    """PoolQuotaStore，用于单地址配额限制。"""
    health_prober: Any = None
    """PoolHealthProber，用于注册地址池到健康探测任务。"""
    trace_enabled: bool = True
    """是否采集规则条件命中明细（写 ``decision_traces`` 冷表）。"""
    trace_sample_rate: float = 0.01
    """trusted 流量的明细采样率；非 trusted 一律全量留痕。"""


class DecisionService:
    """决策服务门面。"""

    def __init__(self, deps: DecisionServiceDeps) -> None:
        self._deps = deps
        self._publish_tasks: set[asyncio.Task[None]] = set()
        """在飞的事件发布任务。

        必须持一份强引用：``asyncio.create_task`` 返回的 Task 只被事件循环弱
        引用，本地变量出作用域后 GC 可能在协程跑完前回收它，事件就静默消失了
        （连日志都不会有）。set + done callback 是官方文档给的标准解法，同时
        让 :meth:`drain_events` 有东西可等。
        """

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        ctx = request.context
        if ctx.ip is None:
            # 到这一步 IP 必须已由接入层填好（SDK 路径取 socket peer，Adapter 路径
            # schema 强制必填）。放过 None 的后果不是报错而是静默污染：下游大量
            # `str(ctx.ip)` 会得到字符串 "None"，让所有缺 IP 的请求共用同一条
            # 决策缓存、同一个频控计数器和同一个封禁键——一次误封会波及全部访客。
            raise ValueError("decide() 收到未解析 IP 的上下文：接入层必须先填充 context.ip")
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        decision_requests_total.labels(app_id=str(ctx.app_id), verdict="pending").inc()

        # Stage: whitelist（最前，误封兜底通道）
        wl_outcome = await self._run_whitelist(ctx)
        if wl_outcome is not None:
            cost_ms = int((time.perf_counter() - started) * 1000)
            # 不传 shadow：本分支在规则匹配之前短路，此刻**还没有**影子数据，
            # 补一个空列表不是丢数据而是如实反映「没评估过」。要在这里测算影响面
            # 就得为白名单流量跑一遍画像构建 + 规则匹配，等于抵消掉这条短路的
            # 全部收益。后果：影子影响面报表不含白名单流量，读数时应理解为
            # 「进入规则匹配的流量里的占比」而非全站占比。其余短路分支同理。
            response = await self._respond(
                disposition=wl_outcome.disposition,
                ctx=ctx,
                request_id=request_id,
                score=wl_outcome.score,
                rule_ids=wl_outcome.rule_ids,
                reason=wl_outcome.reason,
                decided_by=wl_outcome.decided_by.value,
                decided_stage=wl_outcome.decided_stage,
                details=self._details(wl_outcome) if request.require_details else [],
            )
            self._schedule_event(ctx, response, wl_outcome, None, cost_ms)
            decision_requests_total.labels(
                app_id=str(ctx.app_id),
                verdict=wl_outcome.disposition.verdict.value,
            ).inc()
            return response

        # Stage: challenge_pass（白名单之后、频控之前，已完成挑战的访客直接放行）
        pass_outcome = await self._run_challenge_pass(ctx)
        if pass_outcome is not None:
            cost_ms = int((time.perf_counter() - started) * 1000)
            # 同白名单分支：规则匹配未发生，影子影响面在此有意不测算。
            response = await self._respond(
                disposition=pass_outcome.disposition,
                ctx=ctx,
                request_id=request_id,
                score=pass_outcome.score,
                rule_ids=pass_outcome.rule_ids,
                reason=pass_outcome.reason,
                decided_by=pass_outcome.decided_by.value,
                decided_stage=pass_outcome.decided_stage,
                details=self._details(pass_outcome) if request.require_details else [],
            )
            self._schedule_event(ctx, response, pass_outcome, None, cost_ms)
            decision_requests_total.labels(
                app_id=str(ctx.app_id),
                verdict=pass_outcome.disposition.verdict.value,
            ).inc()
            return response

        # Stage: clock（前置于缓存，保证每个请求都被计数）
        clock_outcome = await self._run_clock(ctx)
        if clock_outcome is not None:
            cost_ms = int((time.perf_counter() - started) * 1000)
            # 同白名单分支：频控拦截要尽可能便宜，不为影子测算做规则匹配。
            response = await self._respond(
                disposition=clock_outcome.disposition,
                ctx=ctx,
                request_id=request_id,
                score=clock_outcome.score,
                rule_ids=clock_outcome.rule_ids,
                reason=clock_outcome.reason,
                decided_by=clock_outcome.decided_by.value,
                decided_stage=clock_outcome.decided_stage,
                details=self._details(clock_outcome) if request.require_details else [],
            )
            self._schedule_event(ctx, response, clock_outcome, None, cost_ms)
            decision_requests_total.labels(
                app_id=str(ctx.app_id),
                verdict=clock_outcome.disposition.verdict.value,
            ).inc()
            return response

        # Stage: hybrid_lookup
        # SDK 请求携带 serverToken 时查询第一层预判。
        # - 第一层已拦截（非 pass）→ 直接短路，跳过指纹流水线（兜底更精确的结论）
        # - 第一层 pass → 把信号注入 ctx.extra 供评分阶段参考（不短路）
        hybrid_outcome = await self._run_hybrid_lookup(ctx)
        if hybrid_outcome is not None:
            cost_ms = int((time.perf_counter() - started) * 1000)
            # 同白名单分支：第一层已给出结论，第二层不再跑规则匹配，
            # 因此这条流量也不参与影子影响面测算。
            response = await self._respond(
                disposition=hybrid_outcome.disposition,
                ctx=ctx,
                request_id=request_id,
                score=hybrid_outcome.score,
                rule_ids=hybrid_outcome.rule_ids,
                reason=hybrid_outcome.reason,
                decided_by=hybrid_outcome.decided_by.value,
                decided_stage=hybrid_outcome.decided_stage,
                details=self._details(hybrid_outcome) if request.require_details else [],
            )
            self._schedule_event(ctx, response, hybrid_outcome, None, cost_ms)
            decision_requests_total.labels(
                app_id=str(ctx.app_id),
                verdict=hybrid_outcome.disposition.verdict.value,
            ).inc()
            return response

        cached = await self._try_cache(ctx)
        if cached is not None:
            decision_cache_hits_total.labels(app_id=str(ctx.app_id), layer="decision").inc()
            cached_outcome = self._outcome_from_cache(cached)
            cached_resp = await self._respond(
                disposition=cached.disposition,
                ctx=ctx,
                request_id=request_id,
                score=cached.score,
                rule_ids=tuple(cached.rule_ids),
                reason=cached.reason,
                decided_by=cached.decided_by,
                decided_stage=PipelineStage.CACHE.value,
                # 影子命中来自原次完整评估、随缓存一起存下来的，不是重新算的。
                shadow=self._shadow(cached_outcome),
            )
            # adapter 请求携带 serverToken 时，即使命中缓存也要把结论写入
            # ServerSessionCache，否则 SDK 二次请求的 hybrid_lookup 永远查不到。
            await self._save_server_session(ctx, cached_outcome)
            # cost_ms 在 _respond 之后测：缓存命中路径的耗时几乎全在这里
            # （地址池选址、配额、serve_alt 取页、挑战签发都要打 Redis），
            # 在 _try_cache 之后就取会得到一个恒等于 0 的假数据。
            cost_ms = int((time.perf_counter() - started) * 1000)
            # 缓存命中也必须发事件。此前直接 return，稳态下缓存命中是流量主体，
            # 于是 ClickHouse 里的事件数远少于真实请求数——所有按「总量」做分母
            # 的下游全被系统性拉偏，尤其离线 IP/设备信誉计算（拦截数 / 总数）
            # 会因为分母缺失而把信誉分算高。
            self._schedule_event(ctx, cached_resp, cached_outcome, None, cost_ms)
            return cached_resp

        snapshot = await self._build_snapshot(ctx)
        outcome = await self._run_pipeline(ctx, snapshot)
        outcome = await self._attach_condition_traces(ctx, snapshot, outcome)

        if outcome.is_cacheable:
            await self._deps.decision_cache.set(
                ctx.app_id,
                ctx.fingerprint,
                str(ctx.ip),
                CachedDecision(
                    disposition=outcome.disposition,
                    score=outcome.score,
                    ruleIds=list(outcome.rule_ids),
                    reason=outcome.reason,
                    decidedBy=outcome.decided_by.value,
                    decidedStage=outcome.decided_stage,
                    # 影子命中随决策一起缓存：后续缓存命中就能复用这次评估的
                    # 影响面数据，不必为了测算而重跑规则匹配。
                    shadowHits=[
                        CachedShadowHit(
                            ruleId=h.rule_id,
                            ruleName=h.rule_name,
                            verdict=h.verdict,
                            mechanism=h.mechanism,
                        )
                        for h in outcome.shadow_hits
                    ],
                ),
            )

        # Hybrid 存储：adapter 请求完成决策后，把结论存入 server_session_cache
        # 供后续 SDK 二次请求的 HYBRID_LOOKUP 阶段复用。
        await self._save_server_session(ctx, outcome)

        cost_ms = int((time.perf_counter() - started) * 1000)
        response = await self._respond(
            disposition=outcome.disposition,
            ctx=ctx,
            request_id=request_id,
            score=outcome.score,
            rule_ids=outcome.rule_ids,
            reason=outcome.reason,
            decided_by=outcome.decided_by.value,
            decided_stage=outcome.decided_stage,
            snapshot=snapshot,
            details=self._details(outcome) if request.require_details else [],
            shadow=self._shadow(outcome),
        )
        self._schedule_event(ctx, response, outcome, snapshot, cost_ms)

        decision_requests_total.labels(
            app_id=str(ctx.app_id), verdict=outcome.disposition.verdict.value
        ).inc()
        return response

    async def _run_hybrid_lookup(self, ctx: DecisionContext) -> DecisionOutcome | None:
        """Hybrid 查询阶段（仅 SDK 请求）。

        从 context.extra["serverToken"] 取出第一层会话 token，查询 Redis 中存储的
        adapter 预判结果：
        - 第一层判定为非 pass（hostile / suspect 且机制为拦截）→ 构造 outcome 短路流水线
        - 第一层判定为 pass → 把信号注入 ctx.extra["serverLayer"] 供评分参考，返回 None
        - token 不存在 / 缓存未命中 → 返回 None（流水线正常继续）

        只对 ingress=sdk 的请求生效；adapter 请求本身就是第一层，不做查询。
        """
        from fangyu_shared.schemas.decision import IngressKind

        if ctx.ingress != IngressKind.SDK:
            return None
        cache = self._deps.server_session_cache
        if cache is None:
            return None
        token = ctx.extra.get("serverToken") if ctx.extra else None
        if not token or not isinstance(token, str):
            return None

        entry = await cache.get(token)
        if entry is None:
            return None

        # 消费后删除：防止同一 token 被多次请求复用（防重放）
        await cache.delete(token)

        # 把第一层信号写入 ctx.extra，供 profile/scoring 阶段参考
        object.__setattr__(
            ctx,
            "extra",
            {**ctx.extra, "serverLayer": {
                "verdict": entry.verdict,
                "score": entry.score,
                "ip": entry.ip,
            }},
        )

        # 短路条件：第一层由规则命中（decided_by=decision_rule），说明管理员明确配置了拦截。
        # 纯评分产生的 suspect/hostile 只注入信号，让第二层用真实指纹重新判断。
        if (
            entry.verdict != Verdict.TRUSTED.value
            and entry.decided_by == DecidedBy.DECISION_RULE.value
        ):
            mech = entry.mechanism or Mechanism.CHALLENGE.value
            if mech == Mechanism.DENY.value:
                disp = deny()
            else:
                disp = challenge()

            resolved = DispositionResolver.from_server_layer(
                disp, reason=f"server_layer:{entry.reason or entry.verdict}"
            )
            stage = PipelineStageResult(
                stage=PipelineStage.HYBRID_LOOKUP,
                disposition=resolved.disposition,
                reason=resolved.reason,
                matched=True,
                metadata={"serverScore": entry.score, "serverIp": entry.ip, "serverVerdict": entry.verdict},
            )
            return DecisionOutcome(
                disposition=resolved.disposition,
                decided_by=resolved.decided_by,
                decided_stage=resolved.decided_stage,
                score=entry.score,
                reason=resolved.explain,
                stage_results=(stage,),
            )

        return None  # trusted：第一层已放行，继续完整流水线

    async def _save_server_session(
        self, ctx: DecisionContext, outcome: DecisionOutcome
    ) -> None:
        """Hybrid 存储（仅 adapter 请求）。

        adapter 完成决策后把结论写入 ServerSessionCache，供后续 SDK 请求的
        HYBRID_LOOKUP 阶段读取。token 从 context.extra["serverToken"] 取得。
        """
        from fangyu_shared.schemas.decision import IngressKind

        if ctx.ingress != IngressKind.ADAPTER:
            return
        cache = self._deps.server_session_cache
        if cache is None:
            return
        token = ctx.extra.get("serverToken") if ctx.extra else None
        if not token or not isinstance(token, str):
            return

        from src.infrastructure.cache.server_session_cache import ServerSessionEntry

        entry = ServerSessionEntry(
            verdict=outcome.disposition.verdict.value,
            mechanism=outcome.disposition.mechanism.value,
            decided_by=outcome.decided_by.value,
            score=outcome.score,
            reason=outcome.reason,
            ip=str(ctx.ip) if ctx.ip else "",
            user_agent=ctx.user_agent or "",
        )
        try:
            await cache.set(token, entry)
        except Exception as exc:
            _logger.warning("server_session_cache_set_failed", error=str(exc))

    async def _run_whitelist(self, ctx: DecisionContext) -> DecisionOutcome | None:
        """白名单阶段：命中则放行并终止流水线。

        返回 ``None`` 表示未命中（继续后续阶段）。
        """
        reader = self._deps.whitelist_reader
        if reader is None:
            return None

        with decision_latency_seconds.labels(
            app_id=str(ctx.app_id), stage="whitelist"
        ).time():
            hit = await reader.check(
                ctx.app_id, ip=str(ctx.ip), fingerprint=ctx.fingerprint
            )
        if not hit.matched:
            return None

        resolved = DispositionResolver.from_whitelist(reason=hit.reason)
        stage = PipelineStageResult(
            stage=PipelineStage.WHITELIST,
            disposition=resolved.disposition,
            reason=resolved.reason,
            matched=True,
            metadata={"note": hit.note} if hit.note else {},
        )
        return DecisionOutcome(
            disposition=resolved.disposition,
            decided_by=resolved.decided_by,
            decided_stage=resolved.decided_stage,
            score=0.0,
            reason=resolved.explain,
            stage_results=(stage,),
        )

    async def _run_challenge_pass(self, ctx: DecisionContext) -> DecisionOutcome | None:
        """挑战通行阶段：检查访客是否持有挑战通行凭据。

        返回 ``None`` 表示未持有（继续后续阶段）；返回 outcome 表示持有凭据，直接放行。
        """
        store = self._deps.challenge_pass_store
        if store is None or not ctx.fingerprint:
            return None

        with decision_latency_seconds.labels(
            app_id=str(ctx.app_id), stage="challenge_pass"
        ).time():
            has_pass = await store.check(ctx.app_id, ctx.fingerprint)
        if not has_pass:
            return None

        # 持有通行凭据，直接放行
        resolved = DispositionResolver.from_challenge_pass()
        stage = PipelineStageResult(
            stage=PipelineStage.CHALLENGE_PASS,
            disposition=resolved.disposition,
            reason=resolved.reason,
            matched=True,
        )
        return DecisionOutcome(
            disposition=resolved.disposition,
            decided_by=resolved.decided_by,
            decided_stage=resolved.decided_stage,
            score=0.0,
            reason=resolved.explain,
            stage_results=(stage,),
        )

    async def _run_clock(self, ctx: DecisionContext) -> DecisionOutcome | None:
        """Clock 阶段：计数、落行为时序、判定频控。

        返回 ``None`` 表示放行（继续后续阶段）；返回 outcome 表示已终止。
        """
        repo = self._deps.clock_repository
        guard = self._deps.clock_guard
        if repo is None or guard is None:
            return None

        now_ms = utcnow_ms()
        ip_hash = sha256_hex(str(ctx.ip))[:32]

        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="clock").time():
            limits = await repo.get_limits(ctx.app_id)
            reading = await repo.touch_and_read(
                ctx.app_id,
                ip_hash=ip_hash,
                fingerprint=ctx.fingerprint,
                now_ms=now_ms,
            )
            # 行为时序落库与频控判定无关，失败不影响决策。
            if ctx.behavior_events:
                await repo.store_behavior(
                    ctx.app_id, ctx.fingerprint, ctx.behavior_events, now_ms=now_ms
                )
            verdict = guard.evaluate(reading, limits)

        counts = self._clock_counts(reading)
        if not verdict.blocked:
            return None

        # 超限升级为封禁：让后续请求在窗口内也被直接拒绝，
        # 不必每次都重算计数。
        if verdict.is_over_limit and limits.ban_enabled and verdict.breach is not None:
            await repo.ban(
                ctx.app_id,
                verdict.breach.dimension,
                ip_hash
                if verdict.breach.dimension == ClockDimension.IP
                else ctx.fingerprint,
                seconds=limits.ban_seconds,
                reason=verdict.breach.reason,
            )

        return self._clock_outcome(verdict, counts)

    @staticmethod
    def _clock_counts(reading: ClockReading) -> dict[str, int]:
        """扁平化两个维度的窗口计数，键形如 ``ip_burst``。"""
        out: dict[str, int] = {}
        for prefix, dim in (("ip", reading.ip), ("fp", reading.fingerprint)):
            for window_name, count in dim.counts.items():
                out[f"{prefix}_{window_name}"] = count
        return out

    @staticmethod
    def _clock_outcome(verdict: ClockVerdict, counts: dict[str, int]) -> DecisionOutcome:
        """把 Clock 结论转成 DecisionOutcome。

        封禁与超限都用 ``not_found`` 而非 ``deny``：返回 404 不暴露「你被频控了」
        这个信息，避免攻击者据此校准请求速率。
        """
        if verdict.is_banned:
            resolved = DispositionResolver.from_clock_ban(
                not_found(), reason=verdict.ban_reason or "banned"
            )
        else:
            assert verdict.breach is not None
            resolved = DispositionResolver.from_clock_rate_limit(
                not_found(), reason=verdict.breach.reason
            )

        stage = PipelineStageResult(
            stage=PipelineStage.CLOCK,
            disposition=resolved.disposition,
            reason=resolved.reason,
            matched=True,
            metadata=dict(counts),
        )
        return DecisionOutcome(
            disposition=resolved.disposition,
            decided_by=resolved.decided_by,
            decided_stage=resolved.decided_stage,
            score=100.0,
            reason=resolved.explain,
            stage_results=(stage,),
            clock_counts=counts,
            clock_banned=verdict.is_banned,
        )

    async def _try_cache(self, ctx: DecisionContext) -> CachedDecision | None:
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="cache").time():
            return await self._deps.decision_cache.get(ctx.app_id, ctx.fingerprint, str(ctx.ip))

    @staticmethod
    def _outcome_from_cache(cached: CachedDecision) -> DecisionOutcome:
        """把缓存条目还原成 DecisionOutcome，供事件发布与 Hybrid 存储复用。

        ``decided_stage`` 覆写为 ``cache`` 而 ``decided_by`` 保持原值，是为了让
        下游能区分「这条事件是缓存服务的」：
        - ClickHouse 的 ``decided_stage`` 列已存在且是 LowCardinality(String)，
          直接承载 ``cache`` 不需要加列，也不需要动 schema 版本；
        - ``decided_by`` 回答的是「为什么是这个处置」，改掉它等于抹掉原始拦截
          原因，排障时反而更糟。两个字段合起来读作「当初由 X 判定、这次由缓存
          服务」，正是排障需要的信息量。

        ``decided_by`` 无法解析成枚举时退回 ``SYSTEM_DEFAULT``。写入侧一律用
        ``outcome.decided_by.value``，正常不会走到这里；留着是防手工改过的
        缓存条目——为了一个脏字符串让整条事件发不出去不值得。
        """
        try:
            decided_by = DecidedBy(cached.decided_by)
        except ValueError:
            decided_by = DecidedBy.SYSTEM_DEFAULT
        return DecisionOutcome(
            disposition=cached.disposition,
            decided_by=decided_by,
            decided_stage=PipelineStage.CACHE.value,
            score=cached.score,
            rule_ids=tuple(cached.rule_ids),
            reason=cached.reason,
            shadow_hits=tuple(
                ShadowHit(
                    rule_id=h.rule_id,
                    rule_name=h.rule_name,
                    verdict=h.verdict,
                    mechanism=h.mechanism,
                )
                for h in cached.shadow_hits
            ),
        )

    async def _build_snapshot(self, ctx: DecisionContext) -> ProfileSnapshot:
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="profile").time():
            device = await self._deps.profile_cache.get_device(ctx.app_id, ctx.fingerprint)
            # IP 画像按 app_id 分键：声誉分是「本站点观测到的拦截率」的结论，
            # 不是 IP 的客观属性。读侧必须与回流任务的写侧同键，否则查不到数据
            # 且不会报错——IpReputationScorer 只会一直走 no_reputation_data。
            ip_profile = await self._deps.profile_cache.get_ip(ctx.app_id, str(ctx.ip))
            ip_lookup = self._deps.mmdb_reader.lookup(str(ctx.ip))
            intel = None
            if self._deps.intel_reader is not None:
                intel = await self._deps.intel_reader.lookup(
                    ip=str(ctx.ip),
                    asn=ip_lookup.get("asn"),
                    fingerprint=ctx.fingerprint,
                    user_agent=ctx.user_agent or "",
                )
            return self._deps.profile_builder.build(
                ctx,
                cached_device=device,
                cached_ip=ip_profile,
                ip_lookup=ip_lookup,
                intel=intel,
            )

    async def _run_pipeline(
        self, ctx: DecisionContext, snapshot: ProfileSnapshot
    ) -> DecisionOutcome:
        stages: list[PipelineStageResult] = []
        eval_ctx = snapshot.to_evaluation_context()

        # Stage: decision rule
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="rule").time():
            rule_set = await self._deps.rule_repository.get_rule_set(ctx.app_id)
            match = self._deps.rule_matcher.match(
                rule_set.decision_rules, eval_ctx, groups=rule_set.groups
            )

        shadow_hits = tuple(
            ShadowHit.from_disposition(
                rule_id=m.rule.id,
                rule_name=m.rule.name,
                disposition=m.rule.effective_match_disposition,
            )
            for m in match.shadow_matches
        )

        if match.matched and match.rule is not None:
            resolved = DispositionResolver.from_rule(
                match.rule.effective_match_disposition,
                rule_id=match.rule.id,
                rule_name=match.rule.name,
            )
            stages.append(
                PipelineStageResult(
                    stage=PipelineStage.DECISION_RULE,
                    disposition=resolved.disposition,
                    rule_ids=(match.rule.id,) if match.rule.id else (),
                    reason=resolved.explain,
                    matched=True,
                )
            )
            return self._finalize(resolved, stages, shadow_hits=shadow_hits)

        if match.is_group_no_match and match.group is not None:
            assert match.group.on_no_match is not None  # RuleGroup 校验器已保证
            resolved = DispositionResolver.from_group_no_match(
                match.group.on_no_match, group_name=match.group.name
            )
            stages.append(
                PipelineStageResult(
                    stage=PipelineStage.DECISION_RULE,
                    disposition=resolved.disposition,
                    reason=resolved.explain,
                    matched=True,
                )
            )
            return self._finalize(resolved, stages, shadow_hits=shadow_hits)

        # disposition_miss 短路：规则未命中但带有明确的"未命中处置"
        if match.miss_rule is not None:
            miss_disp = match.miss_rule.effective_miss_disposition
            if miss_disp is not None:
                resolved = DispositionResolver.from_rule(
                    miss_disp,
                    rule_id=match.miss_rule.id,
                    rule_name=match.miss_rule.name,
                    stage="decision_rule_miss",
                )
                stages.append(
                    PipelineStageResult(
                        stage=PipelineStage.DECISION_RULE,
                        disposition=resolved.disposition,
                        rule_ids=(match.miss_rule.id,) if match.miss_rule.id else (),
                        reason=f"miss:{resolved.explain}",
                        matched=True,
                    )
                )
                return self._finalize(resolved, stages, shadow_hits=shadow_hits)

        # Stage: threat intel
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="threat_intel").time():
            ti = await ThreatIntelReader.check(str(ctx.ip))
        if ti.is_threat:
            reason = f"threat_intel:{','.join(ti.categories)}" if ti.categories else "threat_intel"
            resolved = DispositionResolver.from_threat_intel(deny(), reason=reason)
            stages.append(
                PipelineStageResult(
                    stage=PipelineStage.THREAT_INTEL,
                    disposition=resolved.disposition,
                    reason=reason,
                    matched=True,
                    metadata={"categories": ti.categories},
                )
            )
            return self._finalize(
                resolved, stages, score=100.0, shadow_hits=shadow_hits
            )

        # Stage: security
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="security").time():
            sec = self._deps.security_checker.check(snapshot)
        if sec.triggered and sec.disposition is not None:
            resolved = DispositionResolver.from_security(
                sec.disposition, reason=sec.reason or "security"
            )
            stages.append(
                PipelineStageResult(
                    stage=PipelineStage.SECURITY,
                    disposition=resolved.disposition,
                    reason=sec.reason,
                    matched=True,
                )
            )
            return self._finalize(resolved, stages, shadow_hits=shadow_hits)

        # Stage: risk scoring
        # 传入 scoring_rules：权重由后台维护，标定阈值不必改代码重新部署。
        # 评分开关与阈值来自 ScoringConfigCache（admin 保存后 30s 内生效）。
        scoring_cfg = None
        if self._deps.scoring_config_cache is not None:
            scoring_cfg = await self._deps.scoring_config_cache.get(ctx.app_id)

        if scoring_cfg is not None and not scoring_cfg.enabled:
            # 评分已关闭：跳过此阶段，直接交给默认处置链
            stages.append(
                PipelineStageResult(
                    stage=PipelineStage.RISK_SCORING,
                    disposition=rule_set.default_disposition or allow(),
                    reason="scoring_disabled",
                    matched=False,
                )
            )
            resolved = DispositionResolver.fallback(rule_set.default_disposition)
            return self._finalize(resolved, stages, shadow_hits=shadow_hits)

        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="risk").time():
            risk = self._deps.risk_pipeline.run(
                snapshot,
                challenge_threshold=scoring_cfg.challenge_threshold if scoring_cfg else None,
                block_threshold=scoring_cfg.block_threshold if scoring_cfg else None,
                weights=scoring_cfg.weights if scoring_cfg else None,
            )
        reason = ";".join(risk.reasons) if risk.reasons else None
        stages.append(
            PipelineStageResult(
                stage=PipelineStage.RISK_SCORING,
                disposition=risk.disposition,
                score=risk.score,
                reason=reason,
                matched=risk.disposition.is_terminal,
            )
        )

        if risk.disposition.is_terminal:
            # 自定义处置：当分数越线时用 admin 配置的处置覆盖 pipeline 内置的
            final_disp = risk.disposition
            if scoring_cfg is not None:
                if risk.score >= (scoring_cfg.block_threshold):
                    final_disp = scoring_cfg.disposition_hostile or risk.disposition
                elif risk.score >= (scoring_cfg.challenge_threshold):
                    final_disp = scoring_cfg.disposition_suspect or risk.disposition
            resolved = DispositionResolver.from_scoring(final_disp, reason=reason)
        else:
            # 评分未越线：交给默认处置链，而不是直接用评分产出的 allow。
            # 这样 app 级默认配置才有机会生效。
            resolved = DispositionResolver.fallback(rule_set.default_disposition)

        return self._finalize(
            resolved,
            stages,
            score=risk.score,
            scorer_scores=risk.scorer_scores,
            shadow_hits=shadow_hits,
        )

    @staticmethod
    def _finalize(
        resolved: ResolvedDisposition,
        stages: list[PipelineStageResult],
        *,
        score: float = 0.0,
        scorer_scores: dict[str, float] | None = None,
        shadow_hits: tuple[ShadowHit, ...] = (),
    ) -> DecisionOutcome:
        return DecisionOutcome(
            disposition=resolved.disposition,
            decided_by=resolved.decided_by,
            decided_stage=resolved.decided_stage,
            score=score,
            rule_ids=(resolved.rule_id,) if resolved.rule_id else (),
            reason=resolved.explain,
            stage_results=tuple(stages),
            scorer_scores=scorer_scores or {},
            shadow_hits=shadow_hits,
        )

    async def _attach_condition_traces(
        self,
        ctx: DecisionContext,
        snapshot: ProfileSnapshot,
        outcome: DecisionOutcome,
    ) -> DecisionOutcome:
        """按采样策略补上规则条件命中明细，供 worker 写 ``decision_traces``。

        为什么在这里做而不是在匹配器里
        ------------------------------
        匹配器的 ``_hits`` 只返回 bool，逐条件的实际值在算子层就被丢掉了。要在
        匹配时留下明细，就得给**每个请求的每条规则的每个条件**都构造一条记录，
        而其中 99% 的流量既不写库也不会有人查。这里改为决策完成后、只对已经
        决定要留痕的请求重算一遍——重算安全，因为 ``read_path`` 与
        ``apply_operator`` 都是纯函数，同样的 context 必然得到同样的结论。

        为什么不在这里写 ClickHouse
        ---------------------------
        明细只挂到事件上，由 worker 批量写入。gateway 侧再开一路同步 CH 写入会
        把 ClickHouse 的 P99 加进每一次决策的 P99，与「事件发布不在关键路径上」
        的既有取舍矛盾。

        失败一律 fail-open：留痕是排障辅助，不值得为它让决策失败。
        """
        if not self._deps.trace_enabled:
            return outcome
        if not should_trace(
            verdict_is_trusted=outcome.disposition.verdict == Verdict.TRUSTED,
            sample_rate=self._deps.trace_sample_rate,
        ):
            return outcome

        try:
            rule_set = await self._deps.rule_repository.get_rule_set(ctx.app_id)
            # 只对参与过求值的规则重算：匹配器跳过非 active/shadow 的规则，
            # 且不提前 break（影子规则要完整评估），因此这个筛选与它实际算过的
            # 集合一致。给没参与决策的规则留痕只会放大写入量。
            evaluated = [r for r in rule_set.decision_rules if r.is_active or r.is_shadow]
            if not evaluated:
                return outcome
            traces = collect_condition_traces(evaluated, snapshot.to_evaluation_context())
            if not traces:
                return outcome
            return replace(outcome, condition_traces=tuple(traces))
        except Exception as exc:
            _logger.warning("collect_condition_traces_failed", error=str(exc))
            return outcome

    @staticmethod
    def _render(
        *,
        disposition: Disposition,
        ctx: DecisionContext,
        request_id: str,
        score: float,
        rule_ids: tuple[int, ...],
        reason: str | None,
        decided_by: str,
        decided_stage: str,
        snapshot: ProfileSnapshot | None = None,
        details: list[DecisionDetail] | None = None,
        shadow: list[ShadowOutcome] | None = None,
        pool_order: list[str] | None = None,
    ) -> DecisionResponse:
        """构造响应：在此渲染 target_url 占位符。

        渲染失败（协议非法等）时降级为不跳转，避免把 ``javascript:`` 之类的
        协议回给客户端。

        ``snapshot`` 用于提取 IP 画像字段（country / connection_type / is_vpn /
        is_proxy）供占位符渲染；缓存命中和 Clock 阶段没有 snapshot，
        这些变量置空，规则侧应避免在不依赖地理信息的跳转规则里使用它们。

        ``pool_order`` 是轮询策略已排好序的候选地址。为 None 时走 ``url_pool``
        的旧路径（单地址或旧版 urls 字段）。
        """
        ip_profile = snapshot.ip if snapshot else None
        rendered_url = render_pool(
            pool_order if pool_order is not None else disposition.target.url_pool,
            # request_id 每请求唯一，轮询因此按请求分摊而非按访客分片。
            seed=request_id or f"{ctx.app_id}:{ctx.fingerprint}",
            visit_url=ctx.visit_url or ctx.path,
            app_id=ctx.app_id,
            request_id=request_id,
            ip=str(ctx.ip) if ctx.ip else "",
            fingerprint=ctx.fingerprint or "",
            country=ip_profile.country or "" if ip_profile else "",
            verdict=disposition.verdict.value,
            score=score,
            connection_type=ip_profile.connection_type or "" if ip_profile else "",
            is_vpn=ip_profile.is_vpn if ip_profile else False,
            is_proxy=ip_profile.is_proxy if ip_profile else False,
            user_agent=ctx.user_agent or "",
            referer=ctx.referer or "",
            ingress=ctx.ingress.value,
        )
        mechanism = disposition.mechanism
        if mechanism == Mechanism.REDIRECT and not rendered_url:
            # 跳转目标渲染失败：降级放行，不能把半成品地址发出去。
            # 状态码必须跟着重算，否则会下发 mechanism=pass 却 httpStatus=302
            # 这对自相矛盾的值，适配器若以 httpStatus 为准就会跳到空地址。
            mechanism = Mechanism.PASS

        return DecisionResponse(
            verdict=disposition.verdict,
            mechanism=mechanism,
            targetKind=disposition.target.kind,
            targetUrl=rendered_url,
            httpStatus=resolve_http_status(mechanism, disposition.target),
            challengeKind=disposition.challenge_kind,
            score=score,
            ruleIds=list(rule_ids),
            reason=reason,
            decidedBy=decided_by,
            decidedStage=decided_stage,
            ttlSeconds=disposition.ttl_seconds,
            details=details or [],
            shadow=shadow or [],
            requestId=request_id,
        )

    @staticmethod
    def _details(outcome: DecisionOutcome) -> list[DecisionDetail]:
        return [
            DecisionDetail(
                stage=sr.stage.value,
                ruleId=sr.rule_ids[0] if sr.rule_ids else None,
                score=sr.score,
                reason=sr.reason,
            )
            for sr in outcome.stage_results
        ]

    @staticmethod
    def _shadow(outcome: DecisionOutcome) -> list[ShadowOutcome]:
        return [
            ShadowOutcome(
                ruleId=hit.rule_id,
                ruleName=hit.rule_name,
                verdict=hit.verdict,
                mechanism=hit.mechanism,
            )
            for hit in outcome.shadow_hits
        ]

    async def _respond(
        self,
        *,
        disposition: Disposition,
        ctx: DecisionContext,
        request_id: str,
        score: float,
        rule_ids: tuple[int, ...],
        reason: str | None,
        decided_by: str,
        decided_stage: str,
        snapshot: ProfileSnapshot | None = None,
        details: list[DecisionDetail] | None = None,
        shadow: list[ShadowOutcome] | None = None,
    ) -> DecisionResponse:
        """响应构造唯一出口：渲染 + serve_alt 内容富化。

        所有决策路径都必须走这里。此前 _enrich_serve_alt 按分支逐个调用，
        白名单短路分支漏配——虽然当前白名单硬编码 allow() 而无实际后果，
        但一旦白名单支持自定义处置就会立刻显现为「配了替代页却不投放」。
        """
        pool_order = await self._resolve_pool_order(
            disposition, ctx, request_id=request_id, rule_ids=rule_ids
        )
        response = self._render(
            disposition=disposition,
            ctx=ctx,
            request_id=request_id,
            score=score,
            rule_ids=rule_ids,
            reason=reason,
            decided_by=decided_by,
            decided_stage=decided_stage,
            snapshot=snapshot,
            details=details,
            shadow=shadow,
            pool_order=pool_order,
        )
        # 轮询选址成功后消费配额
        await self._consume_pool_quota(disposition, ctx, response.target_url)
        response = await self._enrich_serve_alt(response, disposition, ctx.app_id)
        # 挑战凭据必须在此签发：客户端拿不到 token 就无法调 /challenge/verify，
        # ChallengePassStore 永远不会 grant，整条挑战链路会静默失效。
        return await self._sign_challenge_token(response, disposition, ctx)

    async def _resolve_pool_order(
        self,
        disposition: Disposition,
        ctx: DecisionContext,
        *,
        request_id: str,
        rule_ids: tuple[int, ...],
    ) -> list[str] | None:
        """按轮询策略解析地址优先顺序。返回 None 表示不走轮询（单地址快路径）。

        独立成异步方法是因为 round_robin 需要 Redis 计数器、failover 需要查
        健康状态，而 ``_render`` 是同步的纯函数——把 IO 留在这里，渲染仍可
        在无 Redis 的单测里直接调用。
        """
        target = disposition.target
        if target.kind != TargetKind.URL_POOL or target.rotation is None:
            return None

        rotation = target.rotation
        strategy = rotation.strategy.value
        entries = [(e.url, e.weight, e.enabled) for e in rotation.entries]

        # failover 策略依赖健康检查，注册地址池到探测任务
        if strategy == "failover" and self._deps.health_prober is not None:
            urls = [e.url for e in rotation.entries]
            self._deps.health_prober.register_pool(ctx.app_id, urls)

        counter: int | None = None
        if strategy == "round_robin" and self._deps.rotation_counter is not None:
            # 每条规则一个计数器；无规则 id（默认处置等）时退化为 app 级
            rule_id = rule_ids[0] if rule_ids else 0
            try:
                counter = await self._deps.rotation_counter.next(ctx.app_id, rule_id)
            except Exception:  # noqa: BLE001 - 计数器不可用不该让决策失败
                _logger.warning("rotation_counter unavailable, fallback to hash")
                counter = None

        healthy_fn = None
        store = self._deps.pool_health_store
        if strategy == "failover" and store is not None:
            # 一次性把池内健康状态查完，避免在排序回调里发起 IO
            health_map: dict[str, bool] = {}
            for url, _, _ in entries:
                try:
                    health_map[url] = await store.is_healthy(ctx.app_id, url)
                except Exception:  # noqa: BLE001 - 探测数据缺失时乐观放行
                    health_map[url] = True
            healthy_fn = lambda u: health_map.get(u, True)  # noqa: E731

        # 批量查询配额状态
        exhausted_fn = None
        quota_store = self._deps.pool_quota_store
        if quota_store is not None:
            exhausted_map: dict[str, bool] = {}
            for entry in rotation.entries:
                url = entry.url
                # 任一维度打满即视为耗尽
                daily_exhausted = False
                hourly_exhausted = False
                try:
                    if entry.daily_quota is not None and entry.daily_quota > 0:
                        daily_exhausted = await quota_store.is_exhausted(
                            ctx.app_id, url, entry.daily_quota, "daily"
                        )
                    if entry.hourly_quota is not None and entry.hourly_quota > 0:
                        hourly_exhausted = await quota_store.is_exhausted(
                            ctx.app_id, url, entry.hourly_quota, "hourly"
                        )
                except Exception:  # noqa: BLE001 - 配额查询失败不该让决策失败
                    _logger.warning("pool_quota_store unavailable for %s", url)
                exhausted_map[url] = daily_exhausted or hourly_exhausted
            exhausted_fn = lambda u: exhausted_map.get(u, False)  # noqa: E731

        return resolve_rotation_order(
            entries,
            strategy=strategy,
            request_seed=request_id or f"{ctx.app_id}:{ctx.fingerprint}",
            visitor_seed=ctx.fingerprint or "",
            counter=counter,
            healthy=healthy_fn,
            exhausted=exhausted_fn,
        )

    async def _consume_pool_quota(
        self,
        disposition: Disposition,
        ctx: DecisionContext,
        selected_url: str | None,
    ) -> None:
        """消费已选中地址的配额。

        在渲染之后调用——只有渲染成功才消费，避免占位符非法、协议不匹配等
        导致实际未跳转却扣了配额的不公平现象。
        """
        if selected_url is None:
            return
        target = disposition.target
        if target.kind != TargetKind.URL_POOL or target.rotation is None:
            return
        quota_store = self._deps.pool_quota_store
        if quota_store is None:
            return

        # 找到选中地址对应的配额配置
        entry = next((e for e in target.rotation.entries if e.url == selected_url), None)
        if entry is None:
            return

        # 消费各维度配额（任一超限时 consume 返回 False，但不影响本次响应）
        try:
            if entry.daily_quota is not None and entry.daily_quota > 0:
                await quota_store.consume(ctx.app_id, selected_url, entry.daily_quota, "daily")
            if entry.hourly_quota is not None and entry.hourly_quota > 0:
                await quota_store.consume(ctx.app_id, selected_url, entry.hourly_quota, "hourly")
        except Exception:  # noqa: BLE001 - 配额消费失败不该让响应失败
            _logger.warning("pool_quota_store consume failed for %s", selected_url)

    async def _enrich_serve_alt(
        self,
        response: DecisionResponse,
        disposition: Disposition,
        app_id: int,
    ) -> DecisionResponse:
        """serve_alt 命中时从 Redis 缓存取页面内容并填充 page_content 字段。

        fail-open：缓存未配置或查询失败时静默跳过，page_content 保持 None。
        """
        if disposition.mechanism != Mechanism.SERVE_ALT:
            return response
        cache = self._deps.page_resource_cache
        if cache is None:
            return response
        # target.url 在 serve_alt 语义下是页面资源**名**而非 URL，所以只取池不渲染。
        # 走 pick_target 是为了让 urls 轮询在 serve_alt 上同样成立——否则配了多页
        # 轮询的规则会因为 url 为 None 而静默不投放内容。
        name = pick_target(disposition.target.url_pool, seed=response.request_id or "")
        if not name:
            _logger.warning(
                "serve_alt_no_resource_name",
                app_id=app_id,
                request_id=response.request_id,
                reason="url_pool empty or all disabled",
            )
            return response
        entry = await cache.get(app_id, name)
        if entry is None:
            _logger.warning(
                "serve_alt_resource_not_found",
                app_id=app_id,
                resource_name=name,
                request_id=response.request_id,
            )
            return response
        return response.model_copy(
            update={
                "page_content": entry.content,
                "page_content_type": entry.content_type,
            }
        )

    async def _sign_challenge_token(
        self,
        response: DecisionResponse,
        disposition: Disposition,
        ctx: DecisionContext,
    ) -> DecisionResponse:
        """mechanism=challenge 时签发 HMAC 凭据并填充 challenge_token 字段。

        fail-open：resolver 未配置或查询失败时静默跳过，challenge_token 保持 None。
        客户端拿不到 token 时应退化为普通拦截（显示错误页而非挑战表单）。
        """
        if disposition.mechanism != Mechanism.CHALLENGE:
            return response
        if disposition.challenge_kind is None:
            _logger.warning(
                "challenge_without_kind",
                app_id=ctx.app_id,
                request_id=response.request_id,
                reason="challengeKind is None, cannot issue token",
            )
            return response

        resolver = self._deps.app_key_resolver
        if resolver is None:
            _logger.warning(
                "challenge_token_no_resolver",
                app_id=ctx.app_id,
                request_id=response.request_id,
            )
            return response

        try:
            secret = await resolver.get_secret_by_app_id(ctx.app_id)
            if not secret:
                # 站点未配置 app_secret（或凭据缓存已过期）：无法签发，只能降级。
                # 客户端见 mechanism=challenge 但 challengeToken 为空时应按拦截处理。
                _logger.warning(
                    "challenge_token_no_secret",
                    app_id=ctx.app_id,
                    request_id=response.request_id,
                )
                return response

            token = issue_challenge_token(
                app_id=ctx.app_id,
                fingerprint=ctx.fingerprint or "",
                kind=disposition.challenge_kind.value,
                secret=secret,
                ttl=disposition.ttl_seconds or DEFAULT_CHALLENGE_TTL,
            )
            return response.model_copy(update={"challenge_token": token})

        except Exception as exc:
            _logger.error(
                "challenge_token_sign_error",
                app_id=ctx.app_id,
                request_id=response.request_id,
                error=str(exc),
            )
            return response

    def _schedule_event(
        self,
        ctx: DecisionContext,
        response: DecisionResponse,
        outcome: DecisionOutcome,
        snapshot: ProfileSnapshot | None,
        cost_ms: int,
    ) -> None:
        """把事件发布挪到后台任务，响应不等它。

        同步：只做 create_task，不 await。Redis XADD 的往返因此不再计入
        ``/v2/decide`` 的延迟——事件只供离线分析，让它决定同步决策的 P99 是
        纯粹的浪费。

        ``create_task`` 需要运行中的事件循环。``decide()`` 本身就在协程里，
        正常不会缺；真缺了（有人从同步上下文调）也只丢事件、不影响决策。
        """
        try:
            task = asyncio.create_task(
                self._publish_event(ctx, response, outcome, snapshot, cost_ms)
            )
        except RuntimeError as exc:
            _logger.error("publish_decision_event_unscheduled", error=str(exc))
            return
        self._publish_tasks.add(task)
        # 完成即摘除，否则 set 会随请求量无界增长。discard 而非 remove：
        # drain_events 可能已经把它清掉了。
        task.add_done_callback(self._publish_tasks.discard)

    async def drain_events(self, *, timeout: float = 5.0) -> int:
        """等待在飞的事件发布任务完成，返回等到的任务数。

        关闭时必须调用，否则 lifespan 里 ``RedisManager.close()`` 一执行，
        还没跑到 XADD 的任务会拿到已关闭的连接池——事件丢了，而且丢在「正常
        重启」这种最频繁的场景里。

        ``timeout`` 兜住 Redis 卡死的情况：超时后放弃等待并记日志，不能让关闭
        流程被一个发不出去的事件无限期挂住。已经在飞的任务不取消——它们要么
        自己超时失败，要么在进程退出时随事件循环一起消失。
        """
        pending = list(self._publish_tasks)
        if not pending:
            return 0
        done, still_pending = await asyncio.wait(pending, timeout=timeout)
        if still_pending:
            _logger.warning(
                "drain_decision_events_timeout",
                drained=len(done),
                pending=len(still_pending),
                timeout=timeout,
            )
        return len(done)

    async def _publish_event(
        self,
        ctx: DecisionContext,
        response: DecisionResponse,
        outcome: DecisionOutcome,
        snapshot: ProfileSnapshot | None,
        cost_ms: int,
    ) -> None:
        """发布决策事件。

        ``snapshot`` 为 None 表示 Clock 阶段就终止了，此时还没构建画像——
        MMDB/UA 解析结果留空。这是有意的取舍：频控拦截要尽可能便宜，
        为了补全日志字段而去做一次画像构建不值得。
        """
        try:
            now_ms = utcnow_ms()
            ip = snapshot.ip if snapshot else None
            ua = snapshot.ua if snapshot else None
            event = DecisionEvent(
                eventId=uuid.uuid4().hex,
                appId=ctx.app_id,
                fingerprint=ctx.fingerprint,
                deviceId=ctx.device_id,
                ip=str(ctx.ip),
                ipType="ipv6" if ":" in str(ctx.ip) else "ipv4",
                userAgent=ctx.user_agent,
                path=ctx.path,
                referer=ctx.referer,
                method=ctx.method,
                # 处置三层
                verdict=response.verdict,
                mechanism=response.mechanism,
                targetKind=response.target_kind,
                targetUrl=response.target_url,
                httpStatus=response.http_status,
                # 溯源
                decidedBy=outcome.decided_by.value,
                decidedStage=outcome.decided_stage,
                decidedRuleId=outcome.rule_ids[0] if outcome.rule_ids else None,
                score=outcome.score,
                scorerScores=outcome.scorer_scores,
                ruleIds=list(outcome.rule_ids),
                reason=outcome.reason,
                # 网络解析结果（MMDB 产物）
                country=ip.country if ip else None,
                asn=ip.asn if ip else None,
                connectionType=ip.connection_type if ip else None,
                # 设备解析结果（UA parser 产物）
                deviceType=ua.device_type if ua else None,
                osName=ua.os if ua else None,
                browserName=ua.browser if ua else None,
                isBot=ua.is_bot if ua else False,
                crawlerCategory=ua.crawler_category if ua else None,
                crawlerVendor=ua.crawler_vendor if ua else None,
                # 访客追踪（Evercookie 自愈）
                repeatKey=ctx.repeat_key,
                repeatValue=ctx.repeat_value,
                evercookieRestore=ctx.evercookie_restored,
                # 语言偏好
                acceptLanguage=ctx.client_language,
                # 影子评估
                shadowRuleIds=[h.rule_id for h in outcome.shadow_hits if h.rule_id],
                shadowVerdicts=[h.verdict.value for h in outcome.shadow_hits],
                # 规则条件命中明细（采样后才非空），由 worker 写 decision_traces
                conditionTraces=[
                    ConditionTraceEvent(
                        ruleId=t.rule_id,
                        ruleName=t.rule_name,
                        field=t.field_path,
                        op=t.op,
                        expected=t.expected,
                        actual=t.actual,
                        matched=t.matched,
                    )
                    for t in outcome.condition_traces
                ],
                # 接入来源与 Clock 计数
                ingress=ctx.ingress.value,
                fingerprintIsDerived=ctx.fingerprint_is_derived,
                clockCounts=outcome.clock_counts,
                clockBanned=outcome.clock_banned,
                behaviorEventCount=len(ctx.behavior_events),
                decisionCostMs=cost_ms,
                requestId=response.request_id,
                # ReplacingMergeTree 需要 event_version 单调递增：使用 UTC 毫秒。
                eventVersion=now_ms,
                extra={"ts_ms": now_ms},
            )
            await self._deps.event_publisher.publish(event)
        except Exception as exc:
            _logger.error("publish_decision_event_failed", error=str(exc))

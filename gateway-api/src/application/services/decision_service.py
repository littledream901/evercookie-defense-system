"""决策服务：编排决策流水线。

流水线阶段（命中即返回，跳过后续）
1. CLOCK          - 频控计数 + 封禁检查（**前置于缓存**，见下）
2. CACHE          - 命中即返回未渲染决策，渲染后响应
3. PROFILE        - 构建设备/IP 画像上下文
4. DECISION_RULE  - 决策规则匹配 + allowlist 组兜底
5. THREAT_INTEL   - IP 威胁情报
6. SECURITY       - 基础安全检查（黑名单/地理围栏/Tor）
7. RISK_SCORING   - 风险评分聚合
8. DEFAULT        - app 级默认 → 系统默认

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
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from fangyu_shared.clock.windows import ClockDimension
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
from fangyu_shared.schemas.disposition import Disposition, Mechanism, deny, not_found
from fangyu_shared.schemas.event import DecisionEvent
from fangyu_shared.schemas.target_render import render_target
from fangyu_shared.utils.crypto import sha256_hex
from fangyu_shared.utils.time import utcnow_ms

from src.domain.clock.guard import ClockGuard, ClockVerdict
from src.domain.decision.disposition import DispositionResolver, ResolvedDisposition
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
from src.infrastructure.cache.decision_cache import CachedDecision, DecisionCache
from src.infrastructure.cache.profile_cache import ProfileCache
from src.infrastructure.clock.repository import ClockReading, ClockRepository
from src.infrastructure.event_publisher.stream_publisher import StreamEventPublisher
from src.infrastructure.mmdb.reader import MMDBReader
from src.infrastructure.rule_repo.rule_repository import RuleRepository
from src.infrastructure.threat_intel.reader import ThreatIntelReader

_logger = get_logger("gateway.decision_service")


@dataclass(slots=True)
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


class DecisionService:
    """决策服务门面。"""

    def __init__(self, deps: DecisionServiceDeps) -> None:
        self._deps = deps

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        ctx = request.context
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        decision_requests_total.labels(app_id=str(ctx.app_id), verdict="pending").inc()

        # Stage: clock（前置于缓存，保证每个请求都被计数）
        clock_outcome = await self._run_clock(ctx)
        if clock_outcome is not None:
            cost_ms = int((time.perf_counter() - started) * 1000)
            response = self._render(
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
            await self._publish_event(ctx, response, clock_outcome, None, cost_ms)
            decision_requests_total.labels(
                app_id=str(ctx.app_id),
                verdict=clock_outcome.disposition.verdict.value,
            ).inc()
            return response

        cached = await self._try_cache(ctx)
        if cached is not None:
            decision_cache_hits_total.labels(app_id=str(ctx.app_id), layer="decision").inc()
            return self._render(
                disposition=cached.disposition,
                ctx=ctx,
                request_id=request_id,
                score=cached.score,
                rule_ids=tuple(cached.rule_ids),
                reason=cached.reason,
                decided_by=cached.decided_by,
                decided_stage=cached.decided_stage,
            )

        snapshot = await self._build_snapshot(ctx)
        outcome = await self._run_pipeline(ctx, snapshot)

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
                ),
            )

        cost_ms = int((time.perf_counter() - started) * 1000)
        response = self._render(
            disposition=outcome.disposition,
            ctx=ctx,
            request_id=request_id,
            score=outcome.score,
            rule_ids=outcome.rule_ids,
            reason=outcome.reason,
            decided_by=outcome.decided_by.value,
            decided_stage=outcome.decided_stage,
            details=self._details(outcome) if request.require_details else [],
            shadow=self._shadow(outcome),
        )
        await self._publish_event(ctx, response, outcome, snapshot, cost_ms)

        decision_requests_total.labels(
            app_id=str(ctx.app_id), verdict=outcome.disposition.verdict.value
        ).inc()
        return response

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

    async def _build_snapshot(self, ctx: DecisionContext) -> ProfileSnapshot:
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="profile").time():
            device = await self._deps.profile_cache.get_device(ctx.app_id, ctx.fingerprint)
            ip_profile = await self._deps.profile_cache.get_ip(str(ctx.ip))
            ip_lookup = self._deps.mmdb_reader.lookup(str(ctx.ip))
            return self._deps.profile_builder.build(
                ctx,
                cached_device=device,
                cached_ip=ip_profile,
                ip_lookup=ip_lookup,
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
            ShadowHit(rule_id=m.rule.id, rule_name=m.rule.name, disposition=m.rule.disposition)
            for m in match.shadow_matches
        )

        if match.matched and match.rule is not None:
            resolved = DispositionResolver.from_rule(
                match.rule.disposition, rule_id=match.rule.id, rule_name=match.rule.name
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
        with decision_latency_seconds.labels(app_id=str(ctx.app_id), stage="risk").time():
            risk = self._deps.risk_pipeline.run(snapshot)
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
            resolved = DispositionResolver.from_scoring(risk.disposition, reason=reason)
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
        details: list[DecisionDetail] | None = None,
        shadow: list[ShadowOutcome] | None = None,
    ) -> DecisionResponse:
        """构造响应：在此渲染 target_url 占位符。

        渲染失败（协议非法等）时降级为不跳转，避免把 ``javascript:`` 之类的
        协议回给客户端。
        """
        rendered_url = render_target(
            disposition.target.url,
            visit_url=ctx.visit_url or ctx.path,
            app_id=ctx.app_id,
            request_id=request_id,
        )
        mechanism = disposition.mechanism
        if mechanism == Mechanism.REDIRECT and not rendered_url:
            # 跳转目标渲染失败：降级放行，不能把半成品地址发出去
            mechanism = Mechanism.PASS

        return DecisionResponse(
            verdict=disposition.verdict,
            mechanism=mechanism,
            targetKind=disposition.target.kind,
            targetUrl=rendered_url,
            httpStatus=disposition.effective_status,
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
                verdict=hit.disposition.verdict,
                mechanism=hit.disposition.mechanism,
            )
            for hit in outcome.shadow_hits
        ]

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
                # 影子评估
                shadowRuleIds=[h.rule_id for h in outcome.shadow_hits if h.rule_id],
                shadowVerdicts=[h.disposition.verdict.value for h in outcome.shadow_hits],
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

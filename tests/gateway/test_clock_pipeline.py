"""Clock 接入流水线的集成测试。

覆盖两条最容易出错、且出错后极难排查的性质：
1. Clock 前置于缓存——缓存命中的请求也必须被计数，否则突发流量漏计
2. 频控结论不写决策缓存——否则窗口滑过后访客仍被拒，且规则侧看不出原因
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.schemas.clock import ClockLimits
from fangyu_shared.schemas.decision import DecisionContext, DecisionRequest, IngressKind
from fangyu_shared.schemas.disposition import Mechanism, Verdict, allow
from fangyu_shared.schemas.rule import RuleSet
from src.application.services.decision_service import DecisionService, DecisionServiceDeps
from src.domain.clock.guard import ClockGuard
from src.domain.decision.disposition import DecidedBy
from src.domain.profile.builder import ProfileBuilder
from src.domain.risk.pipeline import RiskDecision
from src.domain.risk.security import SecurityCheckResult
from src.domain.rule.matcher import MatchResult
from src.infrastructure.cache.decision_cache import CachedDecision
from src.infrastructure.clock.repository import (
    BanState,
    ClockReading,
    DimensionCounts,
)
from src.infrastructure.threat_intel.reader import ThreatIntelReader, ThreatIntelResult


@pytest.fixture(autouse=True)
def _patch_threat_intel():
    """威胁情报走真实 Redis，这里替身掉。

    用 ``patch.object`` 而非字符串目标：字符串会在运行时重新解析 ``src``，
    而 admin-api / gateway-api 共用 ``src`` 顶层包名，全量跑时会解析错包。
    """
    with patch.object(
        ThreatIntelReader,
        "check",
        new=AsyncMock(return_value=ThreatIntelResult(is_threat=False, categories=[])),
    ):
        yield


class _StubClockRepo:
    """可编程的 Clock 仓储替身。"""

    def __init__(self, *, counts: dict[str, int] | None = None, banned: bool = False) -> None:
        self._counts = counts or {"burst": 1, "short": 1, "hour": 1}
        self._banned = banned
        self.touch_calls = 0
        self.behavior_calls: list[int] = []
        self.bans: list[tuple[ClockDimension, str, int]] = []
        self.limits = ClockLimits(appId=1, windows={"burst": 10, "short": 100})

    async def get_limits(self, app_id: int) -> ClockLimits:
        return self.limits

    async def touch_and_read(
        self, app_id: int, *, ip_hash: str, fingerprint: str, now_ms: int
    ) -> ClockReading:
        self.touch_calls += 1
        ban = BanState(banned=True, reason="manual") if self._banned else BanState(banned=False)
        return ClockReading(
            ip=DimensionCounts(ClockDimension.IP, ip_hash, dict(self._counts), ban),
            fingerprint=DimensionCounts(
                ClockDimension.FINGERPRINT, fingerprint, dict(self._counts), BanState(False)
            ),
            now_ms=now_ms,
        )

    async def store_behavior(self, app_id, fingerprint, events, *, now_ms) -> int:
        self.behavior_calls.append(len(events))
        return len(events)

    async def ban(self, app_id, dimension, value, *, seconds, reason) -> None:
        self.bans.append((dimension, value, seconds))


class _StubDecisionCache:
    def __init__(self, hit=None) -> None:
        self._hit = hit
        self.set_calls: list = []
        self.get_calls = 0

    async def get(self, app_id, fingerprint, ip):
        self.get_calls += 1
        return self._hit

    async def set(self, app_id, fingerprint, ip, cached) -> None:
        self.set_calls.append(cached)


class _StubProfileCache:
    async def get_device(self, app_id, fingerprint):
        return None

    async def get_ip(self, app_id, ip):
        return None

    async def set_device(self, *a, **kw) -> None:
        return None

    async def set_ip(self, *a, **kw) -> None:
        return None


class _StubRuleRepo:
    async def get_rule_set(self, app_id):
        return RuleSet(appId=app_id)


class _StubMatcher:
    def match(self, rules, context, groups=None):
        return MatchResult(matched=False)


class _StubSecurity:
    def check(self, *a, **kw):
        return SecurityCheckResult(triggered=False)


class _StubRiskPipeline:
    def run(self, snapshot, scoring_rules=None, **kwargs):
        return RiskDecision(disposition=allow(), score=0.0)


class _StubPublisher:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


class _StubMMDB:
    def lookup(self, ip):
        return {}


def _build_service(
    clock_repo: _StubClockRepo | None,
    *,
    cache: _StubDecisionCache | None = None,
) -> tuple[DecisionService, _StubDecisionCache, _StubPublisher]:
    decision_cache = cache or _StubDecisionCache()
    publisher = _StubPublisher()
    deps = DecisionServiceDeps(
        decision_cache=decision_cache,  # type: ignore[arg-type]
        profile_cache=_StubProfileCache(),  # type: ignore[arg-type]
        rule_repository=_StubRuleRepo(),  # type: ignore[arg-type]
        profile_builder=ProfileBuilder(),
        rule_matcher=_StubMatcher(),  # type: ignore[arg-type]
        security_checker=_StubSecurity(),  # type: ignore[arg-type]
        risk_pipeline=_StubRiskPipeline(),  # type: ignore[arg-type]
        event_publisher=publisher,  # type: ignore[arg-type]
        mmdb_reader=_StubMMDB(),  # type: ignore[arg-type]
        clock_repository=clock_repo,  # type: ignore[arg-type]
        clock_guard=ClockGuard() if clock_repo else None,
    )
    return DecisionService(deps), decision_cache, publisher


def _request(**overrides) -> DecisionRequest:
    payload = {
        "appId": 1,
        "fingerprint": "fp_abc",
        "ip": "203.0.113.7",
        "userAgent": "Mozilla/5.0",
        "path": "/checkout",
    }
    payload.update(overrides)
    return DecisionRequest(context=DecisionContext(**payload))


# ---------- Clock 前置于缓存 ----------
@pytest.mark.asyncio
async def test_clock_runs_before_cache_lookup() -> None:
    """Clock 必须先执行：缓存命中也要计数，否则突发流量漏计。"""
    repo = _StubClockRepo()
    cache = _StubDecisionCache(
        hit=CachedDecision(disposition=allow(), score=0.0, decidedBy="decision_rule")
    )
    service, _, _ = _build_service(repo, cache=cache)

    await service.decide(_request())

    assert repo.touch_calls == 1, "缓存命中路径也必须走 Clock 计数"


@pytest.mark.asyncio
async def test_over_limit_blocks_without_consulting_cache() -> None:
    """超限直接终止，不查缓存。"""
    repo = _StubClockRepo(counts={"burst": 999, "short": 999, "hour": 999})
    cache = _StubDecisionCache()
    service, _, _ = _build_service(repo, cache=cache)

    resp = await service.decide(_request())

    assert cache.get_calls == 0
    assert resp.mechanism == Mechanism.NOT_FOUND


# ---------- 频控结论不进缓存 ----------
@pytest.mark.asyncio
async def test_rate_limit_verdict_not_cached() -> None:
    """频控是时间强相关的，缓存会导致窗口滑过后仍被拒。"""
    repo = _StubClockRepo(counts={"burst": 999, "short": 999, "hour": 999})
    service, cache, _ = _build_service(repo)

    await service.decide(_request())

    assert cache.set_calls == [], "频控结论绝不能写入决策缓存"


@pytest.mark.asyncio
async def test_decided_by_marks_time_sensitive() -> None:
    assert DecidedBy.CLOCK_RATE_LIMIT.is_time_sensitive is True
    assert DecidedBy.CLOCK_BAN.is_time_sensitive is True
    assert DecidedBy.DECISION_RULE.is_time_sensitive is False


# ---------- 处置形状 ----------
@pytest.mark.asyncio
async def test_rate_limit_returns_404_not_403() -> None:
    """返回 404 不暴露「你被频控了」，避免攻击者据此校准速率。"""
    repo = _StubClockRepo(counts={"burst": 999, "short": 999, "hour": 999})
    service, _, _ = _build_service(repo)

    resp = await service.decide(_request())

    assert resp.http_status == 404
    assert resp.verdict == Verdict.HOSTILE


@pytest.mark.asyncio
async def test_ban_short_circuits_pipeline() -> None:
    repo = _StubClockRepo(banned=True)
    service, cache, _ = _build_service(repo)

    resp = await service.decide(_request())

    assert resp.mechanism == Mechanism.NOT_FOUND
    assert cache.set_calls == []


# ---------- 超限升级为封禁 ----------
@pytest.mark.asyncio
async def test_over_limit_escalates_to_ban() -> None:
    repo = _StubClockRepo(counts={"burst": 999, "short": 999, "hour": 999})
    service, _, _ = _build_service(repo)

    await service.decide(_request())

    assert len(repo.bans) == 1
    dimension, _, seconds = repo.bans[0]
    assert dimension == ClockDimension.IP
    assert seconds == repo.limits.ban_seconds


@pytest.mark.asyncio
async def test_ban_skipped_when_disabled() -> None:
    repo = _StubClockRepo(counts={"burst": 999, "short": 999, "hour": 999})
    repo.limits = ClockLimits(appId=1, windows={"burst": 10}, banEnabled=False)
    service, _, _ = _build_service(repo)

    await service.decide(_request())

    assert repo.bans == []


# ---------- 行为时序 ----------
@pytest.mark.asyncio
async def test_behavior_events_stored() -> None:
    repo = _StubClockRepo()
    service, _, _ = _build_service(repo)

    await service.decide(
        _request(
            behaviorEvents=[
                {"kind": "click", "clientTsMs": 1_700_000_000_000},
                {"kind": "scroll", "clientTsMs": 1_700_000_000_100},
            ]
        )
    )

    assert repo.behavior_calls == [2]


@pytest.mark.asyncio
async def test_no_behavior_events_skips_store() -> None:
    repo = _StubClockRepo()
    service, _, _ = _build_service(repo)

    await service.decide(_request())

    assert repo.behavior_calls == []


# ---------- Clock 关闭 ----------
@pytest.mark.asyncio
async def test_clock_disabled_skips_stage() -> None:
    """clock_repository=None 时流水线从 CACHE 开始，不产生 Clock 开销。"""
    service, cache, _ = _build_service(None)

    resp = await service.decide(_request())

    assert cache.get_calls == 1
    assert resp.verdict == Verdict.TRUSTED


# ---------- 事件落库 ----------
@pytest.mark.asyncio
async def test_clock_counts_published_in_event() -> None:
    """计数必须落库，否则无法回答「阈值设多少合适」。"""
    repo = _StubClockRepo(counts={"burst": 999, "short": 999, "hour": 999})
    service, _, publisher = _build_service(repo)

    await service.decide(_request())
    # 事件发布已挪出决策关键路径，响应返回时任务可能还没跑。
    await service.drain_events()

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.clock_counts["ip_burst"] == 999
    assert event.decided_by == DecidedBy.CLOCK_RATE_LIMIT.value


@pytest.mark.asyncio
async def test_ingress_recorded_in_event() -> None:
    repo = _StubClockRepo()
    service, _, publisher = _build_service(repo)

    await service.decide(
        _request(ingress=IngressKind.ADAPTER.value, fingerprint="")
    )
    await service.drain_events()

    event = publisher.events[0]
    assert event.ingress == "adapter"
    assert event.fingerprint_is_derived is True


# ---------- 缓存命中也要落库 ----------
@pytest.mark.asyncio
async def test_cache_hit_publishes_event() -> None:
    """缓存命中不发事件会让 ClickHouse 少掉稳态下的大部分流量。

    直接后果是所有以「总请求数」为分母的下游被系统性拉偏——离线 IP/设备信誉
    按「拦截数 / 总数」算，分母缺失会把信誉分算高。
    """
    repo = _StubClockRepo()
    cache = _StubDecisionCache(
        hit=CachedDecision(disposition=allow(), score=12.0, decidedBy="decision_rule")
    )
    service, _, publisher = _build_service(repo, cache=cache)

    await service.decide(_request())
    await service.drain_events()

    assert len(publisher.events) == 1
    event = publisher.events[0]
    # decided_stage 标成 cache 让下游能识别缓存服务的事件；decided_by 保留
    # 原始判定来源，否则排障时看不出当初为什么是这个处置。
    assert event.decided_stage == "cache"
    assert event.decided_by == "decision_rule"
    assert event.score == 12.0

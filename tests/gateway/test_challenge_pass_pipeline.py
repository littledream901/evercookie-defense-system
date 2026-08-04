"""挑战通行凭据的流水线接入测试。

挑战闭环的最后一环：访客在 /v2/challenge/verify 通过校验后拿到通行凭据，
后续请求必须直接放行。覆盖三条出错后不会有任何报错的性质：

1. 持有凭据即放行，且不再计入频控——否则「过了挑战仍被反复挑战」
2. 凭据结论不写决策缓存——否则凭据 TTL 到期后仍有一个缓存周期的放行窗口
3. 排在白名单之后、频控之前——位置错了等于凭据不生效
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.schemas.clock import ClockLimits
from fangyu_shared.schemas.decision import DecisionContext, DecisionRequest
from fangyu_shared.schemas.disposition import Mechanism, Verdict, allow
from fangyu_shared.schemas.rule import RuleSet
from src.application.services.decision_service import (
    DecisionService,
    DecisionServiceDeps,
)
from src.domain.clock.guard import ClockGuard
from src.domain.decision.disposition import DecidedBy
from src.domain.profile.builder import ProfileBuilder
from src.domain.risk.pipeline import RiskDecision
from src.domain.risk.security import SecurityCheckResult
from src.domain.rule.matcher import MatchResult
from src.infrastructure.clock.repository import (
    BanState,
    ClockReading,
    DimensionCounts,
)
from src.infrastructure.threat_intel.reader import ThreatIntelReader, ThreatIntelResult

_IP = "203.0.113.9"
_FP = "fp_passed"


@pytest.fixture(autouse=True)
def _patch_threat_intel():
    with patch.object(
        ThreatIntelReader,
        "check",
        new=AsyncMock(return_value=ThreatIntelResult(is_threat=False, categories=[])),
    ):
        yield


class _StubPassStore:
    """挑战通行凭据存储替身，记录查询参数。"""

    def __init__(self, *, granted: bool = False) -> None:
        self.granted = granted
        self.calls: list[tuple[int, str]] = []

    async def check(self, app_id: int, fingerprint: str) -> bool:
        self.calls.append((app_id, fingerprint))
        return self.granted


class _StubClockRepo:
    def __init__(self, *, banned: bool = False) -> None:
        self.banned = banned
        self.touch_calls = 0
        self.limits = ClockLimits(appId=1, windows={"burst": 10, "short": 100})

    async def get_limits(self, app_id):
        return self.limits

    async def touch_and_read(self, app_id, *, ip_hash, fingerprint, now_ms):
        self.touch_calls += 1
        ban = BanState(banned=True, reason="manual") if self.banned else BanState(False)
        counts = {"burst": 1, "short": 1, "hour": 1}
        return ClockReading(
            ip=DimensionCounts(ClockDimension.IP, ip_hash, dict(counts), ban),
            fingerprint=DimensionCounts(
                ClockDimension.FINGERPRINT, fingerprint, dict(counts), BanState(False)
            ),
            now_ms=now_ms,
        )

    async def store_behavior(self, *a, **kw) -> int:
        return 0

    async def ban(self, *a, **kw) -> None:
        return None


class _StubDecisionCache:
    def __init__(self) -> None:
        self.set_calls: list = []
        self.get_calls = 0

    async def get(self, app_id, fingerprint, ip):
        self.get_calls += 1

    async def set(self, app_id, fingerprint, ip, cached) -> None:
        self.set_calls.append(cached)


class _StubProfileCache:
    async def get_device(self, app_id, fingerprint):
        return None

    async def get_ip(self, app_id, ip):
        return None


class _StubRuleRepo:
    async def get_rule_set(self, app_id):
        return RuleSet(appId=app_id)


class _StubMatcher:
    def match(self, rules, context, groups=None):
        return MatchResult(matched=False)


class _StubSecurity:
    def __init__(self) -> None:
        self.calls = 0

    def check(self, *a, **kw):
        self.calls += 1
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
    *,
    granted: bool = False,
    banned: bool = False,
):
    """构建 DecisionService，注入 challenge_pass_store。"""
    cache = _StubDecisionCache()
    publisher = _StubPublisher()
    clock_repo = _StubClockRepo(banned=banned)
    security = _StubSecurity()
    pass_store = _StubPassStore(granted=granted)
    deps = DecisionServiceDeps(
        decision_cache=cache,  # type: ignore[arg-type]
        profile_cache=_StubProfileCache(),  # type: ignore[arg-type]
        rule_repository=_StubRuleRepo(),  # type: ignore[arg-type]
        profile_builder=ProfileBuilder(),
        rule_matcher=_StubMatcher(),  # type: ignore[arg-type]
        security_checker=security,  # type: ignore[arg-type]
        risk_pipeline=_StubRiskPipeline(),  # type: ignore[arg-type]
        event_publisher=publisher,  # type: ignore[arg-type]
        mmdb_reader=_StubMMDB(),  # type: ignore[arg-type]
        clock_repository=clock_repo,  # type: ignore[arg-type]
        clock_guard=ClockGuard(),
        challenge_pass_store=pass_store,  # type: ignore[arg-type]
    )
    return DecisionService(deps), cache, publisher, clock_repo, security, pass_store


def _request(**overrides) -> DecisionRequest:
    payload = {
        "appId": 1,
        "fingerprint": _FP,
        "ip": _IP,
        "userAgent": "Mozilla/5.0",
        "path": "/verify",
    }
    payload.update(overrides)
    return DecisionRequest(context=DecisionContext(**payload))


@pytest.mark.asyncio
async def test_challenge_pass_allows_and_short_circuits() -> None:
    """持有通行凭据的访客直接放行，且不计入频控。"""
    service, cache, _, clock_repo, security, pass_store = _build_service(granted=True)

    resp = await service.decide(_request())

    assert resp.verdict == Verdict.TRUSTED
    assert resp.mechanism == Mechanism.PASS
    assert resp.decided_stage == "challenge_pass"
    assert len(pass_store.calls) == 1
    assert pass_store.calls[0] == (1, _FP)
    assert cache.get_calls == 0, "凭据命中不该再查缓存"
    assert clock_repo.touch_calls == 0, "凭据流量不参与频控计数"
    assert security.calls == 0


@pytest.mark.asyncio
async def test_challenge_pass_verdict_not_cached() -> None:
    """凭据结论不缓存，否则凭据 TTL 到期后仍有一个缓存周期的放行窗口。"""
    service, cache, _, _, _, _ = _build_service(granted=True)

    await service.decide(_request())

    assert cache.set_calls == []


def test_challenge_pass_decided_by_is_time_sensitive() -> None:
    """凭据是时间敏感的，不该被决策缓存留存。"""
    assert DecidedBy.CHALLENGE_PASS.is_time_sensitive is True


@pytest.mark.asyncio
async def test_no_pass_continues_pipeline() -> None:
    """未持有凭据时继续后续阶段，不短路。"""
    service, _, _, clock_repo, _, pass_store = _build_service(granted=False)

    resp = await service.decide(_request())

    assert resp.decided_stage != "challenge_pass"
    assert len(pass_store.calls) == 1  # 仍然查了一次
    assert clock_repo.touch_calls == 1  # 继续走频控


@pytest.mark.asyncio
async def test_challenge_pass_hit_published_to_event() -> None:
    """凭据放行也要落库，否则日志里表现为一个凭空通过的请求。"""
    service, _, publisher, _, _, _ = _build_service(granted=True)

    await service.decide(_request())
    # 事件发布已挪出决策关键路径，响应返回时任务可能还没跑。
    await service.drain_events()

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.verdict == Verdict.TRUSTED.value
    assert event.decided_stage == "challenge_pass"

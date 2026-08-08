"""白名单阶段的读取与流水线接入测试。

覆盖三条最容易出错、且出错后不会有任何报错的性质：
1. 白名单排在最前——被频控封禁的访客也必须能被白名单救回
2. 白名单结论不写决策缓存——否则删除后仍有一个 TTL 周期的放行窗口
3. IP 键用明文而非哈希——写入侧一旦「顺手统一成哈希」，白名单静默失效
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import orjson
import pytest
from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.schemas.clock import ClockLimits
from fangyu_shared.schemas.decision import DecisionContext, DecisionRequest
from fangyu_shared.schemas.disposition import Mechanism, Verdict, allow
from fangyu_shared.schemas.rule import RuleSet
from fangyu_shared.whitelist.keys import (
    WhitelistDimension,
    field_name,
    parse_field,
    whitelist_key,
)
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
from src.infrastructure.whitelist.reader import WhitelistReader

_IP = "203.0.113.7"
_FP = "fp_abc"


@pytest.fixture(autouse=True)
def _patch_threat_intel():
    with patch.object(
        ThreatIntelReader,
        "check",
        new=AsyncMock(return_value=ThreatIntelResult(is_threat=False, categories=[])),
    ):
        yield


class _FakeRedis:
    """只实现 HMGET 的 Redis 替身，记录被查询的 key/field。"""

    def __init__(self, entries: dict[str, bytes] | None = None, *, fail: bool = False) -> None:
        self._entries = entries or {}
        self._fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    async def hmget(self, key: str, fields: list[str]):
        if self._fail:
            raise ConnectionError("redis down")
        self.calls.append((key, list(fields)))
        return [self._entries.get(f) for f in fields]


def _meta(note: str = "") -> bytes:
    return orjson.dumps({"note": note, "createdBy": "1", "createdAtMs": 1})


# ---------- 键构造 ----------
def test_field_roundtrip() -> None:
    field = field_name(WhitelistDimension.IP, _IP)
    assert field == f"ip:{_IP}"
    assert parse_field(field) == (WhitelistDimension.IP, _IP)


def test_parse_field_keeps_colons_in_value() -> None:
    """IPv6 与含冒号的指纹不能被切碎。"""
    field = field_name(WhitelistDimension.IP, "2001:db8::1")
    assert parse_field(field) == (WhitelistDimension.IP, "2001:db8::1")


def test_parse_field_rejects_garbage() -> None:
    """脏 field 返回 None 而非抛异常，否则列表页打不开就删不掉它。"""
    assert parse_field("nonsense") is None
    assert parse_field("unknown:value") is None
    assert parse_field("ip:") is None


def test_whitelist_key_shape() -> None:
    assert whitelist_key(7) == "fangyu:whitelist:7"


# ---------- Reader ----------
@pytest.mark.asyncio
async def test_ip_hit() -> None:
    redis = _FakeRedis({f"ip:{_IP}": _meta("办公网出口")})
    hit = await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]

    assert hit.matched is True
    assert hit.dimension is WhitelistDimension.IP
    assert hit.value == _IP
    assert hit.note == "办公网出口"
    assert hit.reason == f"whitelist:ip:{_IP}"


@pytest.mark.asyncio
async def test_fingerprint_hit() -> None:
    redis = _FakeRedis({f"fp:{_FP}": _meta()})
    hit = await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]

    assert hit.matched is True
    assert hit.dimension is WhitelistDimension.FINGERPRINT
    assert hit.value == _FP


@pytest.mark.asyncio
async def test_miss() -> None:
    redis = _FakeRedis({})
    hit = await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]
    assert hit.matched is False
    assert hit.reason == "whitelist"


@pytest.mark.asyncio
async def test_single_roundtrip_for_both_dimensions() -> None:
    """两条轴一次 HMGET 取回，不是两次 SISMEMBER。"""
    redis = _FakeRedis({})
    await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]

    assert len(redis.calls) == 1
    key, fields = redis.calls[0]
    assert key == "fangyu:whitelist:1"
    assert fields == [f"ip:{_IP}", f"fp:{_FP}"]


@pytest.mark.asyncio
async def test_ip_queried_as_plaintext_not_hash() -> None:
    """IP 走明文。改成哈希会让所有已录入的白名单静默失效。"""
    redis = _FakeRedis({})
    await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]

    _, fields = redis.calls[0]
    assert _IP in fields[0], "IP field 必须含明文 IP"


@pytest.mark.asyncio
async def test_redis_failure_is_miss_not_hit() -> None:
    """Redis 故障按未命中处理：按命中处理等于 Redis 一挂全站风控停摆。"""
    redis = _FakeRedis(fail=True)
    hit = await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]
    assert hit.matched is False


@pytest.mark.asyncio
async def test_broken_meta_still_hits() -> None:
    """元信息坏掉不该把放行变成 500——手工 HSET 调试后很常见。"""
    redis = _FakeRedis({f"ip:{_IP}": b"not-json"})
    hit = await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]

    assert hit.matched is True
    assert hit.note == ""


@pytest.mark.asyncio
async def test_ip_wins_over_fingerprint() -> None:
    redis = _FakeRedis({f"ip:{_IP}": _meta("ip"), f"fp:{_FP}": _meta("fp")})
    hit = await WhitelistReader(redis).check(1, ip=_IP, fingerprint=_FP)  # type: ignore[arg-type]
    assert hit.dimension is WhitelistDimension.IP


# ---------- 流水线接入 ----------
class _StubClockRepo:
    def __init__(self, *, banned: bool = False) -> None:
        self.banned = banned
        self.touch_calls = 0
        self.limits = ClockLimits(siteId=1, windows={"burst": 10, "short": 100})

    async def get_limits(self, site_id):
        return self.limits

    async def touch_and_read(self, site_id, *, ip_hash, fingerprint, now_ms):
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

    async def get(self, site_id, fingerprint, ip):
        self.get_calls += 1

    async def set(self, site_id, fingerprint, ip, cached) -> None:
        self.set_calls.append(cached)


class _StubProfileCache:
    async def get_device(self, site_id, fingerprint):
        return None

    async def get_ip(self, site_id, ip):
        return None


class _StubRuleRepo:
    async def get_rule_set(self, site_id):
        return RuleSet(siteId=site_id)


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
    entries: dict[str, bytes] | None = None,
    whitelist: bool = True,
    banned: bool = False,
):
    cache = _StubDecisionCache()
    publisher = _StubPublisher()
    clock_repo = _StubClockRepo(banned=banned)
    security = _StubSecurity()
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
        whitelist_reader=(
            WhitelistReader(_FakeRedis(entries or {}))  # type: ignore[arg-type]
            if whitelist
            else None
        ),
    )
    return DecisionService(deps), cache, publisher, clock_repo, security


def _request(**overrides) -> DecisionRequest:
    payload = {
        "siteId": 1,
        "fingerprint": _FP,
        "ip": _IP,
        "userAgent": "Mozilla/5.0",
        "path": "/checkout",
    }
    payload.update(overrides)
    return DecisionRequest(context=DecisionContext(**payload))


@pytest.mark.asyncio
async def test_whitelist_allows_and_short_circuits() -> None:
    service, cache, _, clock_repo, security = _build_service(
        entries={f"ip:{_IP}": _meta("办公网")}
    )

    resp = await service.decide(_request())

    assert resp.verdict == Verdict.TRUSTED
    assert resp.mechanism == Mechanism.PASS
    assert resp.decided_stage == "whitelist"
    assert cache.get_calls == 0, "白名单命中不该再查缓存"
    assert clock_repo.touch_calls == 0, "白名单流量不参与频控计数"
    assert security.calls == 0


@pytest.mark.asyncio
async def test_whitelist_rescues_banned_visitor() -> None:
    """白名单必须排在频控之前，否则误封无从解除。

    被封禁的访客连 SecurityChecker 都到不了——「在 SecurityChecker 之前查
    白名单」这个位置是不够的。
    """
    service, _, _, _, _ = _build_service(
        entries={f"ip:{_IP}": _meta()}, banned=True
    )

    resp = await service.decide(_request())

    assert resp.mechanism == Mechanism.PASS


@pytest.mark.asyncio
async def test_banned_without_whitelist_still_blocked() -> None:
    """对照组：白名单为空时封禁照常生效。"""
    service, _, _, _, _ = _build_service(entries={}, banned=True)

    resp = await service.decide(_request())

    assert resp.mechanism == Mechanism.NOT_FOUND


@pytest.mark.asyncio
async def test_whitelist_verdict_not_cached() -> None:
    """缓存了它，删除白名单后仍有一个 TTL 周期的放行窗口。"""
    service, cache, _, _, _ = _build_service(entries={f"ip:{_IP}": _meta()})

    await service.decide(_request())

    assert cache.set_calls == []


def test_whitelist_decided_by_is_time_sensitive() -> None:
    assert DecidedBy.WHITELIST.is_time_sensitive is True


@pytest.mark.asyncio
async def test_whitelist_hit_published_to_event() -> None:
    """放行也要落库，否则日志里表现为一个凭空通过的请求。"""
    service, _, publisher, _, _ = _build_service(entries={f"ip:{_IP}": _meta()})

    await service.decide(_request())
    # 事件发布已挪出决策关键路径，响应返回时任务可能还没跑。
    await service.drain_events()

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event.decided_by == DecidedBy.WHITELIST.value
    assert _IP in (event.reason or "")


@pytest.mark.asyncio
async def test_whitelist_disabled_skips_stage() -> None:
    """whitelist_reader=None 时流水线从 CLOCK 开始。"""
    service, _, _, clock_repo, _ = _build_service(whitelist=False)

    await service.decide(_request())

    assert clock_repo.touch_calls == 1


@pytest.mark.asyncio
async def test_miss_falls_through_to_pipeline() -> None:
    service, cache, _, clock_repo, security = _build_service(entries={})

    resp = await service.decide(_request())

    assert clock_repo.touch_calls == 1
    assert cache.get_calls == 1
    assert security.calls == 1
    assert resp.decided_stage != "whitelist"

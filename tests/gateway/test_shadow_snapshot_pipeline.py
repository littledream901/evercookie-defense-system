"""影子规则从 Redis 快照到决策响应的端到端测试。

与 test_rule_model_matcher.py 的区别：那边直接给匹配器传领域对象，这边走
**真实的 RuleRepository 反序列化路径**（Redis Hash → orjson → 模型），因此能
额外守住两件只在跨进程边界才会暴露的事：

1. status 字段能穿过 admin 的 model_dump_json → gateway 的 model_validate，
   ``rule.is_shadow`` 在读侧仍为 True。这一步一旦丢字段（比如某天给 status
   加了 exclude），影子规则会被当成普通规则**真的去拦流量**。
2. 影子规则进入快照后不改变返回的处置，但确实出现在 shadow 影响面数据里。

快照 payload 用 ``model_dump_json(by_alias=True)`` 生成，与 admin 侧
``RuleCache._payload`` 完全一致的序列化方式（不能直接 import 那个类：admin 与
gateway 都以 ``src`` 为顶层包名，同进程内互斥）。手写 JSON 字面量则会把
「两侧字段契约一致」这件事假设掉，而它恰恰是最该被测的部分。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fangyu_shared.schemas.decision import DecisionContext, DecisionRequest
from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    DecisionDisposition,
    Mechanism,
    Verdict,
    allow,
)
from fangyu_shared.schemas.rule import (
    DecisionRule,
    RuleCondition,
    RuleKind,
    RuleStatus,
)
from src.application.services.decision_service import (
    DecisionService,
    DecisionServiceDeps,
)
from src.domain.profile.builder import ProfileBuilder
from src.domain.risk.pipeline import RiskDecision
from src.domain.risk.security import SecurityCheckResult
from src.domain.rule.matcher import DecisionRuleMatcher
from src.infrastructure.rule_repo.rule_repository import RuleRepository
from src.infrastructure.threat_intel.reader import ThreatIntelReader, ThreatIntelResult

_IP = "203.0.113.7"
_FP = "fp_shadow"
_SITE_ID = 1


@pytest.fixture(autouse=True)
def _patch_threat_intel():
    with patch.object(
        ThreatIntelReader,
        "check",
        new=AsyncMock(return_value=ThreatIntelResult(is_threat=False, categories=[])),
    ):
        yield


def _rule(
    *,
    rid: int,
    status: RuleStatus,
    mechanism: Mechanism,
    country: str = "CN",
    name: str = "r",
) -> DecisionRule:
    return DecisionRule(
        id=rid,
        siteId=_SITE_ID,
        name=name,
        status=status,
        kind=RuleKind.DECISION,
        conditions=[RuleCondition(field="ip.country", op="eq", value=country)],
        # challenge 机制必须带 challenge_kind（DecisionDisposition 的校验器要求），
        # 其余机制则禁止携带，所以这里按机制条件填充
        disposition_match=DecisionDisposition(
            mechanism=mechanism,
            challengeKind=ChallengeKind.JS if mechanism == Mechanism.CHALLENGE else None,
        ),
        disposition_miss=DecisionDisposition(mechanism=Mechanism.PASS),
    )


class _SnapshotRedis:
    """规则分片的 Redis 替身：HGETALL 返回 admin 写入格式的快照。"""

    def __init__(self, rules: list[DecisionRule]) -> None:
        # 与 admin RuleCache._payload 同样的序列化方式
        self._rules = {
            str(r.id): r.model_dump_json(by_alias=True) for r in rules
        }
        self._rules["__version__"] = "1700000000000"

    async def hgetall(self, key: str) -> dict[str, str]:
        if key == f"fangyu:rules:site:{_SITE_ID}":
            return dict(self._rules)
        return {}


class _StubDecisionCache:
    def __init__(self) -> None:
        self.set_calls: list = []

    async def get(self, site_id, fingerprint, ip):
        return None

    async def set(self, site_id, fingerprint, ip, cached) -> None:
        self.set_calls.append(cached)


class _StubProfileCache:
    async def get_device(self, site_id, fingerprint):
        return None

    async def get_ip(self, site_id, ip):
        return None


class _StubSecurity:
    def check(self, *a, **kw):
        return SecurityCheckResult(triggered=False)


class _StubRiskPipeline:
    def run(self, snapshot, **kwargs):
        return RiskDecision(disposition=allow(), score=0.0)


class _StubPublisher:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


class _StubMMDB:
    """把 ip.country 固定成 CN，让规则条件可命中。"""

    def lookup(self, ip):
        return {"country": "CN"}


def _build_service(rules: list[DecisionRule]) -> tuple[DecisionService, _StubDecisionCache]:
    cache = _StubDecisionCache()
    deps = DecisionServiceDeps(
        decision_cache=cache,  # type: ignore[arg-type]
        profile_cache=_StubProfileCache(),  # type: ignore[arg-type]
        # 真实仓储 + 真实匹配器：这条链路正是本测试的对象
        rule_repository=RuleRepository(_SnapshotRedis(rules)),  # type: ignore[arg-type]
        profile_builder=ProfileBuilder(),
        rule_matcher=DecisionRuleMatcher(),
        security_checker=_StubSecurity(),  # type: ignore[arg-type]
        risk_pipeline=_StubRiskPipeline(),  # type: ignore[arg-type]
        event_publisher=_StubPublisher(),  # type: ignore[arg-type]
        mmdb_reader=_StubMMDB(),  # type: ignore[arg-type]
    )
    return DecisionService(deps), cache


def _request() -> DecisionRequest:
    return DecisionRequest(
        context=DecisionContext(
            siteId=_SITE_ID,
            fingerprint=_FP,
            ip=_IP,
            userAgent="Mozilla/5.0",
            path="/checkout",
        )
    )


async def test_snapshot_roundtrip_preserves_shadow_status() -> None:
    """status=shadow 必须活着穿过 Redis 序列化边界。

    这是整条链路的地基：读侧 is_shadow 为 False 时，影子规则会真的去拦流量。
    """
    repo = RuleRepository(
        _SnapshotRedis([_rule(rid=1, status=RuleStatus.SHADOW, mechanism=Mechanism.DENY)])
    )
    rule_set = await repo.get_rule_set(_SITE_ID)

    assert len(rule_set.decision_rules) == 1
    loaded = rule_set.decision_rules[0]
    assert loaded.status == RuleStatus.SHADOW
    assert loaded.is_shadow is True
    assert loaded.is_active is False


async def test_shadow_only_snapshot_does_not_block() -> None:
    """快照里只有一条会命中的 deny 影子规则时，访客仍须被放行。

    这条断言是「影子规则进 Redis」这个改动的安全底线：admin 侧一旦开始下发
    SHADOW，若读侧漏判就等于凭空多出一条生效拦截规则。
    """
    service, _ = _build_service(
        [_rule(rid=1, status=RuleStatus.SHADOW, mechanism=Mechanism.DENY, name="shadow-deny")]
    )

    response = await service.decide(_request())

    assert response.verdict == Verdict.TRUSTED
    assert response.mechanism == Mechanism.PASS


async def test_shadow_hit_reported_in_shadow_field() -> None:
    """影子命中不改处置，但必须出现在 shadow 影响面数据里。"""
    service, _ = _build_service(
        [_rule(rid=1, status=RuleStatus.SHADOW, mechanism=Mechanism.DENY, name="shadow-deny")]
    )

    response = await service.decide(_request())

    assert len(response.shadow) == 1
    assert response.shadow[0].rule_id == 1
    assert response.shadow[0].verdict == Verdict.HOSTILE

    # 处置未被影响，与上一条测试同源但这里同时断言两侧，防止将来有人
    # 为了让 shadow 有数据而顺手把它接进处置链
    assert response.mechanism == Mechanism.PASS


async def test_published_rule_wins_while_shadow_only_records() -> None:
    """published 与 shadow 同时命中时，处置只由 published 决定。"""
    service, _ = _build_service(
        [
            _rule(
                rid=1,
                status=RuleStatus.PUBLISHED,
                mechanism=Mechanism.CHALLENGE,
                name="real-challenge",
            ),
            _rule(
                rid=2,
                status=RuleStatus.SHADOW,
                mechanism=Mechanism.DENY,
                name="shadow-deny",
            ),
        ]
    )

    response = await service.decide(_request())

    assert response.mechanism == Mechanism.CHALLENGE
    assert [s.rule_id for s in response.shadow] == [2]


async def test_shadow_hits_travel_with_decision_cache() -> None:
    """影子影响面随决策一起入缓存，避免下次命中缓存时数据凭空消失。"""
    service, cache = _build_service(
        [_rule(rid=1, status=RuleStatus.SHADOW, mechanism=Mechanism.DENY)]
    )

    await service.decide(_request())

    assert len(cache.set_calls) == 1
    assert [h.rule_id for h in cache.set_calls[0].shadow_hits] == [1]

"""风险评分聚合的回归测试。

重点锁住三条性质，它们是此前加权平均模型的失效点：

1. **单调性**：新增一个不参与判定的 scorer，不得改变既有请求的总分。
2. **强信号不被稀释**：高危组合必须越过拦截线。
3. **权重可配置**：评分配置页下发的权重能覆盖 scorer 类默认值，且支持负权重。
"""

from __future__ import annotations

import pytest
from fangyu_shared.schemas.disposition import Mechanism
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile

from fangyu_shared.ua.parser import UAResult
from src.domain.profile.builder import ProfileSnapshot
from src.domain.risk.pipeline import RiskPipeline
from src.domain.risk.scorers import (
    BehaviorScorer,
    DeviceScorer,
    IpReputationScorer,
    ProxyScorer,
    RiskScorer,
    ScorerOutput,
    UserAgentScorer,
)


def _snapshot(
    *,
    ip: IpProfile | None = None,
    device: DeviceProfile | None = None,
    ua: UAResult | None = None,
    context: dict | None = None,
) -> ProfileSnapshot:
    return ProfileSnapshot(
        device=device or DeviceProfile(fingerprint="fp-test"),
        ip=ip or IpProfile(ip="203.0.113.10"),
        ua=ua,
        context=context or {"request": {"method": "GET", "path": "/"}},
    )


def _pipeline(scorers: list[RiskScorer] | None = None) -> RiskPipeline:
    return RiskPipeline(
        scorers
        or [
            IpReputationScorer(),
            ProxyScorer(),
            UserAgentScorer(),
            DeviceScorer(),
            BehaviorScorer(),
        ],
    )


class _ConstantScorer(RiskScorer):
    """恒定产出的测试 scorer。"""

    def __init__(self, name: str, score: float, *, weight: float = 1.0, applies: bool = True):
        self.name = name
        self.weight = weight
        self._score = score
        self._applies = applies

    def score(self, snapshot: ProfileSnapshot) -> ScorerOutput:
        if not self._applies:
            return self._skip("test_skip")
        return ScorerOutput(
            name=self.name, score=self._score, weight=self.weight, applies=True
        )


# ── 单调性 ──


def test_adding_non_applying_scorer_does_not_change_score():
    """加一个不参与的 scorer 不得改变总分。

    加权平均模型下这里会失败：分母从 1.0 变成 2.0，总分被腰斩。
    """
    base = _pipeline([_ConstantScorer("a", 40.0)])
    extended = _pipeline(
        [_ConstantScorer("a", 40.0), _ConstantScorer("noop", 0.0, applies=False)]
    )
    snapshot = _snapshot()

    assert base.run(snapshot).score == extended.run(snapshot).score == 40.0


def test_adding_positive_signal_never_lowers_score():
    """新增正分信号只能让总分上升或持平，绝不下降。"""
    snapshot = _snapshot()
    before = _pipeline([_ConstantScorer("a", 40.0)]).run(snapshot).score
    after = (
        _pipeline([_ConstantScorer("a", 40.0), _ConstantScorer("b", 15.0)])
        .run(snapshot)
        .score
    )
    assert after >= before


def test_score_is_capped_at_100():
    scorers = [_ConstantScorer(f"s{i}", 80.0) for i in range(5)]
    assert _pipeline(scorers).run(_snapshot()).score == 100.0


def test_score_floors_at_zero_with_negative_weights():
    """负权重不得把总分压到 0 以下。"""
    scorers = [_ConstantScorer("bad", 10.0), _ConstantScorer("trusted", 90.0, weight=-2.0)]
    assert _pipeline(scorers).run(_snapshot()).score == 0.0


# ── 强信号不被稀释 ──


def test_datacenter_plus_new_device_reaches_challenge():
    """数据中心 IP + 全新设备必须至少进挑战。

    加权平均模型下这个组合是 25.0 分，直接放行。
    """
    snapshot = _snapshot(
        ip=IpProfile(ip="198.51.100.7", connectionType="datacenter", isDatacenter=True),
        ua=UAResult(device_type="desktop", os="windows", browser="chrome"),
    )
    decision = _pipeline().run(snapshot)
    assert decision.score >= 30.0
    assert decision.disposition.mechanism is not Mechanism.PASS


def test_library_crawler_on_datacenter_is_blocked():
    """已知爬虫库 UA + 数据中心 IP 必须拦截。

    加权平均模型下是 35.2 分放行 —— 这是最典型的漏放场景。
    """
    snapshot = _snapshot(
        ip=IpProfile(ip="198.51.100.8", connectionType="datacenter", isDatacenter=True),
        ua=UAResult(is_bot=True, crawler_category="library", crawler_vendor="requests"),
    )
    decision = _pipeline().run(snapshot)
    assert decision.score >= 75.0
    assert decision.disposition.mechanism is Mechanism.DENY


def test_no_reputation_data_contributes_nothing():
    """信誉库无数据时 ip_reputation 不得贡献基线分。"""
    snapshot = _snapshot(ua=UAResult(device_type="desktop", os="windows", browser="chrome"))
    decision = _pipeline([IpReputationScorer()]).run(snapshot)

    assert decision.score == 0.0
    assert "ip_reputation" not in decision.scorer_scores


def test_reputation_participates_once_evaluated():
    """有样本时才按信誉分计入。"""
    snapshot = _snapshot(
        ip=IpProfile(ip="203.0.113.11", reputationScore=20.0, reputationSamples=50)
    )
    decision = _pipeline([IpReputationScorer()]).run(snapshot)

    # (100 - 20) * 1.2 = 96
    assert decision.score == 96.0
    assert decision.scorer_scores["ip_reputation"] == 80.0


def test_clean_traffic_passes():
    """正常访客不得被误伤。"""
    snapshot = _snapshot(
        ip=IpProfile(
            ip="203.0.113.12",
            connectionType="residential",
            reputationScore=95.0,
            reputationSamples=200,
        ),
        device=DeviceProfile(
            fingerprint="fp-known",
            totalRequests=120,
            blockedRequests=0,
            reputationScore=95.0,
            reputationSamples=120,
        ),
        ua=UAResult(device_type="desktop", os="windows", browser="chrome"),
    )
    decision = _pipeline().run(snapshot)
    assert decision.score < 30.0
    assert decision.disposition.mechanism is Mechanism.PASS


# ── 权重覆盖（来自评分配置页）──


def test_config_weight_overrides_class_weight():
    """评分配置下发的权重覆盖 scorer 类上的默认权重。

    传入的权重已由 ScoringConfigCache 从整数量纲除以 10 还原，此处直接是浮点倍率。
    """
    pipeline = _pipeline([_ConstantScorer("a", 20.0, weight=1.0)])
    snapshot = _snapshot()

    assert pipeline.run(snapshot).score == 20.0
    assert pipeline.run(snapshot, weights={"a": 3.0}).score == 60.0


def test_negative_config_weight_subtracts():
    """负权重表达可信信号减分。"""
    pipeline = _pipeline(
        [_ConstantScorer("bad", 50.0), _ConstantScorer("verified", 40.0, weight=1.0)]
    )

    # 50 + 40*(-1.0) = 10
    assert pipeline.run(_snapshot(), weights={"verified": -1.0}).score == 10.0


def test_unknown_scorer_name_in_weights_is_ignored():
    """权重表里的陌生 scorer 名不影响既有维度。

    维度 key 与 scorer 名对不上曾导致整页权重静默失效，这里锁住「多余的 key
    只是无效，不会连带破坏正常维度」这个行为。
    """
    pipeline = _pipeline([_ConstantScorer("a", 20.0, weight=1.0)])

    assert pipeline.run(_snapshot(), weights={"not_a_scorer": 9.9}).score == 20.0


def test_partial_weights_keep_class_defaults():
    """只配一部分维度时，未配置的 scorer 沿用类默认权重。"""
    pipeline = _pipeline(
        [_ConstantScorer("a", 10.0, weight=1.0), _ConstantScorer("b", 10.0, weight=2.0)]
    )

    # a 被覆盖为 3.0，b 保持类上的 2.0 → 10*3 + 10*2 = 50
    assert pipeline.run(_snapshot(), weights={"a": 3.0}).score == 50.0


@pytest.mark.parametrize(
    ("score", "mechanism"),
    [
        (10.0, Mechanism.PASS),
        (30.0, Mechanism.CHALLENGE),
        (74.0, Mechanism.CHALLENGE),
        (75.0, Mechanism.DENY),
    ],
)
def test_threshold_boundaries(score: float, mechanism: Mechanism):
    """阈值边界：30 起挑战，75 起拦截，均为闭区间下界。"""
    decision = _pipeline([_ConstantScorer("a", score)]).run(_snapshot())
    assert decision.disposition.mechanism is mechanism

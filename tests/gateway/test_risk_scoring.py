"""风险评分聚合的回归测试。

重点锁住三条性质，它们是此前加权平均模型的失效点：

1. **单调性**：新增一个不参与判定的 scorer，不得改变既有请求的总分。
2. **强信号不被稀释**：高危组合必须越过拦截线。
3. **权重可配置**：评分配置页下发的权重能覆盖 scorer 类默认值，且支持负权重。
4. **配置下发无声失效**：维度 key 与 scorer 名对不上、量纲换算、verdict 推导。
5. **人机行为信号**：脚本流量命中、真人不命中、无行为数据时不参与判定。
"""

from __future__ import annotations

import pytest
from fangyu_shared.clock.behavior import BehaviorKind
from fangyu_shared.schemas.clock import BehaviorEvent
from fangyu_shared.schemas.disposition import Mechanism, Verdict, deny
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile
from fangyu_shared.ua.parser import UAResult
from src.domain.profile.builder import ProfileSnapshot
from src.domain.risk.pipeline import RiskPipeline
from src.domain.risk.scorers import (
    BehaviorScorer,
    DeviceScorer,
    InteractionScorer,
    IpReputationScorer,
    ProxyScorer,
    RiskScorer,
    ScorerOutput,
    UserAgentScorer,
)
from src.infrastructure.cache.scoring_config_cache import (
    _parse_disposition,
    _parse_weights,
)


def _snapshot(
    *,
    ip: IpProfile | None = None,
    device: DeviceProfile | None = None,
    ua: UAResult | None = None,
    context: dict | None = None,
    behavior_events: tuple[BehaviorEvent, ...] = (),
) -> ProfileSnapshot:
    return ProfileSnapshot(
        device=device or DeviceProfile(fingerprint="fp-test"),
        ip=ip or IpProfile(ip="203.0.113.10"),
        ua=ua,
        context=context or {"request": {"method": "GET", "path": "/"}},
        behavior_events=behavior_events,
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


# ── 配置下发：整数量纲还原与 verdict 推导 ──


def test_parse_weights_divides_by_ten():
    """admin 存整数便于滑块步进，网关侧除以 10 还原为 scorer 的浮点量纲。"""
    assert _parse_weights({"proxy": 15, "device": 10}) == {"proxy": 1.5, "device": 1.0}


def test_parse_weights_skips_invalid_entries_only():
    """单个维度写坏时逐项跳过，不得让整表退回默认权重。"""
    assert _parse_weights({"proxy": 15, "device": "bad"}) == {"proxy": 1.5}


def test_parse_weights_tolerates_non_dict():
    """字段缺失或类型不对时返回空表，由 scorer 沿用类默认权重。"""
    assert _parse_weights(None) == {}
    assert _parse_weights("15") == {}


@pytest.mark.parametrize(
    ("raw", "verdict"),
    [
        ({"mechanism": "pass"}, Verdict.TRUSTED),
        ({"mechanism": "challenge", "challengeKind": "captcha"}, Verdict.SUSPECT),
        ({"mechanism": "deny"}, Verdict.HOSTILE),
        ({"mechanism": "not_found"}, Verdict.HOSTILE),
    ],
)
def test_scoring_disposition_verdict_is_derived(raw: dict, verdict: Verdict):
    """评分配置的自定义处置不含 verdict，由 mechanism 推导。

    锁住「选 deny 却标成 trusted」这类口径与行为打架的配置无法进入运行时。
    """
    parsed = _parse_disposition(raw, fallback=deny())
    assert parsed.verdict is verdict


def test_legacy_verdict_key_is_ignored():
    """存量数据里残留的 verdict 键应被忽略，而非覆盖推导结果。

    早期版本存的是完整 Disposition，因此库里可能留有 verdict 字段。
    """
    parsed = _parse_disposition(
        {"mechanism": "deny", "verdict": "trusted"}, fallback=deny()
    )
    assert parsed.verdict is Verdict.HOSTILE


# ── 人机交互特征（InteractionScorer）──

_T0 = 1_700_000_000_000
"""行为事件的基准时间戳。取固定值让间隔计算可复现。"""


def _event(kind: BehaviorKind, offset_ms: int, **data: object) -> BehaviorEvent:
    return BehaviorEvent(kind=kind, clientTsMs=_T0 + offset_ms, data=data)


def _interaction(events: tuple[BehaviorEvent, ...]) -> ScorerOutput:
    return InteractionScorer().score(_snapshot(behavior_events=events))


def test_no_behavior_events_does_not_apply():
    """Adapter 流量结构上不可能有行为事件，必须报「不参与判定」。

    这是本 scorer 最重要的正确性要求：判成可疑会让所有纯服务端接入因为
    「没装浏览器 SDK」被恒定加分。
    """
    output = _interaction(())

    assert output.applies is False
    assert output.score == 0.0
    assert output.reason == "no_behavior_events"


def test_adapter_traffic_contributes_nothing_to_total():
    """无行为数据时不得改变总分，也不得出现在 scorer_scores 里。

    与 test_adding_non_applying_scorer_does_not_change_score 同一条不变量，
    这里用真实的 InteractionScorer 再锁一次。
    """
    snapshot = _snapshot(
        ua=UAResult(device_type="desktop", os="windows", browser="chrome")
    )
    base = _pipeline([_ConstantScorer("a", 40.0)]).run(snapshot).score
    extended = _pipeline([_ConstantScorer("a", 40.0), InteractionScorer()]).run(snapshot)

    assert extended.score == base == 40.0
    assert "interaction" not in extended.scorer_scores


def test_page_view_without_interaction_scores():
    """有页面停留却零交互：无头/脚本流量的典型形状。

    page_view + focus/blur 由页面加载本身产生，鼠标滚动键盘全空。
    """
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        _event(BehaviorKind.FOCUS, 10, stayMs=10),
        _event(BehaviorKind.BLUR, 5_000, stayMs=5_000),
    )
    output = _interaction(events)

    assert output.applies is True
    assert output.score == 20.0
    assert output.reason is not None
    assert "no_interaction" in output.reason


def test_fresh_page_view_alone_is_not_a_signal():
    """首次 decide 紧跟 start()，缓冲区里只有 page_view，跨度约 0。

    此时用户还没有机会操作，不能算信号——否则每个访客的首个请求都被加分。
    """
    output = _interaction((_event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),))

    assert output.applies is True
    assert output.score == 0.0
    assert output.reason is None


def test_single_click_clears_no_interaction_signal():
    """只要有一次真实交互，零交互信号就不该成立。"""
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        _event(BehaviorKind.CLICK, 4_000, x=10, y=20, tag="a"),
    )
    output = _interaction(events)

    assert output.applies is True
    assert output.score == 0.0


def test_metronomic_event_timing_scores():
    """间隔恒定的事件序列＝定时回放。

    setInterval 驱动的脚本 CV 接近 0，真人点击的 CV 普遍在 0.3 以上。
    """
    events = tuple(
        _event(BehaviorKind.CLICK, i * 500, x=5, y=5, tag="div") for i in range(8)
    )
    output = _interaction(events)

    assert output.applies is True
    assert output.reason is not None
    assert "regular_timing" in output.reason
    assert output.score >= 30.0


def test_human_click_jitter_does_not_score():
    """真人点击间隔波动大，不得命中规律性判定。"""
    offsets = [0, 730, 1_950, 2_180, 4_400, 4_620, 7_800, 9_050]
    events = tuple(
        _event(BehaviorKind.CLICK, offset, x=5, y=5, tag="div") for offset in offsets
    )
    output = _interaction(events)

    assert output.applies is True
    assert output.score == 0.0
    assert output.reason is None


def test_sampling_floor_is_not_mistaken_for_bot_regularity():
    """SDK 的 200ms 同类采样地板不得被当成脚本规律性。

    这是最关键的误杀防线：真人连续滑动鼠标时，被采样器放行的点几乎恰好每
    200ms 一个，间隔标准差天然接近 0。若不排除节流类型，所有认真滚动页面的
    真人都会命中 regular_timing。
    """
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        *(
            _event(BehaviorKind.MOUSE_MOVE, 200 + i * 200, x=i * 3, y=i * 2)
            for i in range(20)
        ),
    )
    output = _interaction(events)

    assert output.applies is True
    assert output.score == 0.0
    assert output.reason is None


def test_scroll_at_sampling_floor_is_not_a_signal():
    """滚动同理：节流后的等间隔滚动是真人行为。"""
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        *(
            _event(BehaviorKind.SCROLL, 200 + i * 200, y=i * 120, depth=i * 4)
            for i in range(15)
        ),
    )

    assert _interaction(events).score == 0.0


def test_same_tick_burst_is_not_treated_as_replay():
    """同一 JS tick 内的批量事件间隔接近 0，方差也接近 0。

    这更可能是页面初始化的批量行为而非定时回放，因此平均间隔低于下限时
    不判规律性。
    """
    events = tuple(
        _event(BehaviorKind.CLICK, i * 3, x=1, y=1, tag="div") for i in range(10)
    )

    assert _interaction(events).score == 0.0


def test_too_few_events_cannot_prove_regularity():
    """样本不足时低方差没有统计意义，不得判定。"""
    events = tuple(
        _event(BehaviorKind.CLICK, i * 500, x=5, y=5, tag="div") for i in range(4)
    )

    assert _interaction(events).score == 0.0


def test_all_repeat_key_press_burst_scores():
    """key_press 几乎全带 repeat 标记：长按或伪造载荷。

    刻意只给弱分——真人删长文本也会长按。
    """
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        *(
            _event(
                BehaviorKind.KEY_PRESS, 500 + i * 200, category="letter", repeat=True
            )
            for i in range(10)
        ),
    )
    output = _interaction(events)

    assert output.reason is not None
    assert "key_repeat_burst" in output.reason
    assert output.score == 12.0


def test_normal_typing_does_not_score():
    """正常输入的 repeat 基本为 false，不得命中。"""
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        *(
            _event(
                BehaviorKind.KEY_PRESS, 500 + i * 220, category="letter", repeat=False
            )
            for i in range(12)
        ),
    )

    assert _interaction(events).score == 0.0


def test_scripted_traffic_reaches_challenge_with_weak_network_signal():
    """脚本行为叠加数据中心 IP + 新设备后必须至少进挑战。

    单条行为信号刻意压在挑战线之下（30 × 0.8 = 24），要靠与其他维度累加
    才定性。这里锁住「累加之后确实越线」。
    """
    events = tuple(
        _event(BehaviorKind.CLICK, i * 500, x=5, y=5, tag="div") for i in range(8)
    )
    snapshot = _snapshot(
        ip=IpProfile(ip="198.51.100.9", connectionType="datacenter", isDatacenter=True),
        ua=UAResult(device_type="desktop", os="windows", browser="chrome"),
        behavior_events=events,
    )
    decision = _pipeline(
        [
            IpReputationScorer(),
            ProxyScorer(),
            UserAgentScorer(),
            DeviceScorer(),
            BehaviorScorer(),
            InteractionScorer(),
        ]
    ).run(snapshot)

    assert decision.scorer_scores["interaction"] == 30.0
    assert decision.disposition.mechanism is not Mechanism.PASS


def test_human_browsing_session_stays_clean():
    """完整的真人浏览会话不得被行为维度加一分。"""
    events = (
        _event(BehaviorKind.PAGE_VIEW, 0, url="https://a.test/"),
        _event(BehaviorKind.FOCUS, 120, stayMs=120),
        _event(BehaviorKind.MOUSE_MOVE, 940, x=310, y=222),
        _event(BehaviorKind.MOUSE_MOVE, 1_140, x=402, y=190),
        _event(BehaviorKind.SCROLL, 1_860, y=640, depth=22),
        _event(BehaviorKind.CLICK, 3_310, x=402, y=196, tag="button"),
        _event(BehaviorKind.KEY_PRESS, 4_020, category="letter", repeat=False),
        _event(BehaviorKind.KEY_PRESS, 4_290, category="letter", repeat=False),
        _event(BehaviorKind.SUBMIT, 6_700, method="post", stayMs=6_700),
    )
    output = _interaction(events)

    assert output.applies is True
    assert output.score == 0.0
    assert output.reason is None


def test_behavior_events_reach_snapshot_from_context():
    """行为事件必须真正从 DecisionContext 流到快照，否则 scorer 永远拿不到输入。"""
    from fangyu_shared.schemas.decision import DecisionContext
    from src.domain.profile.builder import ProfileBuilder

    ctx = DecisionContext(
        appId=1,
        fingerprint="fp-behavior",
        ip="203.0.113.30",
        userAgent="Mozilla/5.0",
        behaviorEvents=[
            {"kind": "page_view", "clientTsMs": _T0, "data": {"url": "https://a.test/"}},
            {"kind": "click", "clientTsMs": _T0 + 900, "data": {"tag": "a"}},
        ],
    )
    snapshot = ProfileBuilder().build(ctx)

    assert len(snapshot.behavior_events) == 2
    assert snapshot.behavior_events[0].kind is BehaviorKind.PAGE_VIEW


def test_client_cannot_forge_behavior_events_via_extra():
    """客户端不得通过 extra 伪造评分输入。

    ``extra`` 是客户端可控的自由字典。若行为事件走 context 展开那条路，
    ``extra={"behaviorEvents": []}`` 之类的载荷就能干扰评分输入。这里锁住
    「extra 里的同名键落不进 behavior_events」。
    """
    from fangyu_shared.schemas.decision import DecisionContext
    from src.domain.profile.builder import ProfileBuilder

    ctx = DecisionContext(
        appId=1,
        fingerprint="fp-forge",
        ip="203.0.113.31",
        userAgent="Mozilla/5.0",
        behaviorEvents=[
            {"kind": "page_view", "clientTsMs": _T0, "data": {}},
        ],
        extra={"behaviorEvents": [], "behavior_events": []},
    )
    snapshot = ProfileBuilder().build(ctx)

    assert len(snapshot.behavior_events) == 1
    assert snapshot.behavior_events[0].kind is BehaviorKind.PAGE_VIEW

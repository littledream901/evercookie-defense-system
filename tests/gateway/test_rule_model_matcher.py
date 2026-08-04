"""规则模型拆分与决策匹配器测试。

覆盖三件本次重构的核心保证：
1. 非法字段组合在类型层面构造不出来（weight / disposition 互斥）
2. allowlist 组兜底作用域严格限制在组内
3. 影子规则参与求值但不影响真实决策
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fangyu_shared.schemas.disposition import Mechanism, allow, deny, not_found, observe
from fangyu_shared.schemas.rule import (
    DecisionRule,
    GroupMode,
    RuleCondition,
    RuleGroup,
    RuleKind,
    RulePriority,
    RuleStatus,
    ScoringRule,
)

from src.domain.rule.evaluator import ConditionEvaluator
from src.domain.rule.matcher import DecisionRuleMatcher


def _cond(field: str = "ip.country", op: str = "eq", value: object = "CN") -> RuleCondition:
    return RuleCondition(field=field, op=op, value=value)


def _decision(
    *,
    rid: int,
    name: str = "r",
    status: RuleStatus = RuleStatus.PUBLISHED,
    priority: RulePriority = RulePriority.NORMAL,
    conditions: list[RuleCondition] | None = None,
    disposition=None,
    group: str | None = None,
    match_all: bool = True,
) -> DecisionRule:
    return DecisionRule(
        id=rid,
        appId=1,
        name=name,
        status=status,
        priority=priority,
        conditions=conditions or [_cond()],
        disposition=disposition or deny(),
        group=group,
        matchAll=match_all,
    )


# ---------- 模型：种类互斥 ----------
def test_scoring_rule_has_no_disposition_field() -> None:
    r = ScoringRule(appId=1, name="s", conditions=[_cond()], weight=30)
    assert not hasattr(r, "disposition")
    assert r.kind == RuleKind.SCORING


def test_decision_rule_has_no_weight_field() -> None:
    r = _decision(rid=1)
    assert not hasattr(r, "weight")
    assert r.kind == RuleKind.DECISION


def test_kind_cannot_be_mismatched() -> None:
    with pytest.raises(ValidationError):
        ScoringRule(appId=1, name="s", conditions=[_cond()], weight=1, kind=RuleKind.DECISION)
    with pytest.raises(ValidationError):
        DecisionRule(
            appId=1, name="d", conditions=[_cond()], disposition=deny(), kind=RuleKind.SCORING
        )


def test_empty_conditions_rejected() -> None:
    # fail-closed：旧版空条件规则会命中全部流量
    with pytest.raises(ValidationError):
        DecisionRule(appId=1, name="d", conditions=[], disposition=deny())
    with pytest.raises(ValidationError):
        ScoringRule(appId=1, name="s", conditions=[], weight=10)


def test_invalid_operator_rejected() -> None:
    with pytest.raises(ValidationError):
        _decision(rid=1, conditions=[_cond(op="banana")])


def test_invalid_field_namespace_rejected() -> None:
    with pytest.raises(ValidationError):
        _decision(rid=1, conditions=[_cond(field="foo.bar")])


# ---------- 规则组语义 ----------
def test_allowlist_requires_on_no_match() -> None:
    with pytest.raises(ValidationError):
        RuleGroup(appId=1, name="g", mode=GroupMode.ALLOWLIST)


def test_blocklist_rejects_on_no_match() -> None:
    with pytest.raises(ValidationError):
        RuleGroup(appId=1, name="g", mode=GroupMode.BLOCKLIST, onNoMatch=deny())


# ---------- 匹配器 ----------
@pytest.fixture()
def matcher() -> DecisionRuleMatcher:
    return DecisionRuleMatcher(ConditionEvaluator())


def test_first_match_wins_by_priority(matcher: DecisionRuleMatcher) -> None:
    low = _decision(rid=1, name="low", priority=RulePriority.LOW, disposition=deny())
    critical = _decision(
        rid=2, name="critical", priority=RulePriority.CRITICAL, disposition=allow()
    )
    result = matcher.match([low, critical], {"ip": {"country": "CN"}})
    assert result.matched is True
    assert result.rule is not None
    assert result.rule.name == "critical"


def test_no_match_returns_unmatched(matcher: DecisionRuleMatcher) -> None:
    result = matcher.match([_decision(rid=1)], {"ip": {"country": "US"}})
    assert result.matched is False
    assert result.rule is None


def test_draft_rules_are_ignored(matcher: DecisionRuleMatcher) -> None:
    draft = _decision(rid=1, status=RuleStatus.DRAFT)
    assert matcher.match([draft], {"ip": {"country": "CN"}}).matched is False


def test_disabled_rules_are_ignored(matcher: DecisionRuleMatcher) -> None:
    disabled = _decision(rid=1, status=RuleStatus.DISABLED)
    assert matcher.match([disabled], {"ip": {"country": "CN"}}).matched is False


def test_match_any_semantics(matcher: DecisionRuleMatcher) -> None:
    rule = _decision(
        rid=1,
        match_all=False,
        conditions=[_cond(value="CN"), _cond(value="RU")],
    )
    assert matcher.match([rule], {"ip": {"country": "RU"}}).matched is True


def test_match_all_semantics(matcher: DecisionRuleMatcher) -> None:
    rule = _decision(
        rid=1,
        conditions=[_cond(value="CN"), _cond(field="ua.is_bot", value=True)],
    )
    ctx = {"ip": {"country": "CN"}, "ua": {"is_bot": False}}
    assert matcher.match([rule], ctx).matched is False


# ---------- allowlist 兜底 ----------
def test_allowlist_no_match_applies_group_disposition(matcher: DecisionRuleMatcher) -> None:
    group = RuleGroup(
        appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=not_found()
    )
    member = _decision(rid=1, group="office", conditions=[_cond(value="CN")])
    result = matcher.match([member], {"ip": {"country": "US"}}, groups=[group])
    assert result.matched is True
    assert result.is_group_no_match is True
    assert result.group is not None
    assert result.group.on_no_match.mechanism == Mechanism.NOT_FOUND


def test_allowlist_hit_skips_group_fallback(matcher: DecisionRuleMatcher) -> None:
    group = RuleGroup(appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=deny())
    member = _decision(rid=1, group="office", disposition=allow(), conditions=[_cond(value="CN")])
    result = matcher.match([member], {"ip": {"country": "CN"}}, groups=[group])
    assert result.is_group_no_match is False
    assert result.rule is not None


def test_empty_allowlist_group_does_not_block_everything(matcher: DecisionRuleMatcher) -> None:
    """刚建好还没加规则的白名单组不得拦下全部流量。"""
    group = RuleGroup(appId=1, name="empty", mode=GroupMode.ALLOWLIST, onNoMatch=deny())
    result = matcher.match([], {"ip": {"country": "US"}}, groups=[group])
    assert result.matched is False


def test_group_scope_is_isolated(matcher: DecisionRuleMatcher) -> None:
    """组外规则不参与该组的兜底判定——修掉旧版 on_miss 的全局副作用。"""
    group = RuleGroup(appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=deny())
    outsider = _decision(rid=9, group=None, conditions=[_cond(value="JP")])
    member = _decision(rid=1, group="office", conditions=[_cond(value="CN")])
    result = matcher.match([member, outsider], {"ip": {"country": "US"}}, groups=[group])
    # 组内成员未命中 → 兜底生效，与组外规则无关
    assert result.is_group_no_match is True


def test_disabled_group_is_skipped(matcher: DecisionRuleMatcher) -> None:
    group = RuleGroup(
        appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=deny(), enabled=False
    )
    member = _decision(rid=1, group="office", conditions=[_cond(value="CN")])
    result = matcher.match([member], {"ip": {"country": "US"}}, groups=[group])
    assert result.matched is False


# ---------- 影子评估 ----------
def test_shadow_rule_recorded_but_not_applied(matcher: DecisionRuleMatcher) -> None:
    shadow = _decision(rid=7, name="shadow-block", status=RuleStatus.SHADOW, disposition=deny())
    result = matcher.match([shadow], {"ip": {"country": "CN"}})
    assert result.matched is False
    assert len(result.shadow_matches) == 1
    assert result.shadow_matches[0].rule.id == 7


def test_shadow_recorded_alongside_real_match(matcher: DecisionRuleMatcher) -> None:
    real = _decision(rid=1, name="real", disposition=observe())
    shadow = _decision(rid=2, name="shadow", status=RuleStatus.SHADOW, disposition=deny())
    result = matcher.match([real, shadow], {"ip": {"country": "CN"}})
    assert result.rule is not None
    assert result.rule.id == 1
    assert len(result.shadow_matches) == 1


def test_shadow_miss_not_recorded(matcher: DecisionRuleMatcher) -> None:
    shadow = _decision(rid=2, status=RuleStatus.SHADOW, conditions=[_cond(value="RU")])
    result = matcher.match([shadow], {"ip": {"country": "CN"}})
    assert result.shadow_matches == ()


def test_shadow_never_wins_over_group_no_match(matcher: DecisionRuleMatcher) -> None:
    """影子规则命中也不能顶替 allowlist 组兜底。

    winner 为空时匹配器会转去问兜底，影子命中若被算作 winner，这条流量就会
    拿到影子规则的处置而不是组兜底——影子规则直接改变了真实结果。
    """
    group = RuleGroup(appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=not_found())
    member = _decision(rid=1, group="office", conditions=[_cond(value="CN")])
    shadow = _decision(
        rid=2, name="shadow", status=RuleStatus.SHADOW, disposition=deny(),
        conditions=[_cond(value="US")],
    )
    result = matcher.match([member, shadow], {"ip": {"country": "US"}}, groups=[group])

    # 处置来自组兜底，不是那条命中的影子规则
    assert result.is_group_no_match is True
    assert result.rule is None
    assert result.group is not None
    assert result.group.on_no_match.mechanism == Mechanism.NOT_FOUND
    assert [s.rule.id for s in result.shadow_matches] == [2]


# ---------- 影子规则 × allowlist 组兜底 ----------
def test_shadow_member_does_not_satisfy_allowlist_group(
    matcher: DecisionRuleMatcher,
) -> None:
    """组内影子成员命中，不得抑制该组兜底。

    ``_unmatched_allowlist`` 的成员集合按 ``is_active`` 过滤（SHADOW 为 False），
    所以影子成员不算「白名单放行了这次访问」。反过来若把它算进去，一条还在观察
    期的规则就能让访客绕过白名单兜底——影子规则实打实地改变了真实处置。
    """
    group = RuleGroup(appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=not_found())
    active_member = _decision(rid=1, group="office", conditions=[_cond(value="JP")])
    shadow_member = _decision(
        rid=2, name="shadow", group="office", status=RuleStatus.SHADOW,
        disposition=allow(), conditions=[_cond(value="US")],
    )
    result = matcher.match(
        [active_member, shadow_member], {"ip": {"country": "US"}}, groups=[group]
    )

    # 影子成员命中了，但兜底照旧生效
    assert result.is_group_no_match is True
    assert [s.rule.id for s in result.shadow_matches] == [2]


def test_shadow_only_allowlist_group_stays_inert(matcher: DecisionRuleMatcher) -> None:
    """组内只有影子成员时，该组等同于空组——不得凭空拦下全部流量。

    这是「影子规则开始下发到 Redis」这个改动最危险的副作用面：若成员集合不按
    is_active 过滤，一个只含影子成员的白名单组会突然对所有未命中流量施加
    on_no_match，把观察行为变成全站拦截。
    """
    group = RuleGroup(appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=deny())
    shadow_member = _decision(
        rid=1, name="shadow", group="office", status=RuleStatus.SHADOW,
        disposition=allow(), conditions=[_cond(value="CN")],
    )
    result = matcher.match([shadow_member], {"ip": {"country": "US"}}, groups=[group])

    assert result.matched is False
    assert result.is_group_no_match is False


def test_promoting_member_to_shadow_does_not_change_verdict(
    matcher: DecisionRuleMatcher,
) -> None:
    """把组内成员置为影子，兜底结论必须与该成员处于 draft（不下发）时一致。

    这正是 published→shadow 被状态机禁止的理由所在：一旦允许降级，
    组的兜底面会随之变化，而管理员以为自己只是「转为观察」。
    """
    group = RuleGroup(appId=1, name="office", mode=GroupMode.ALLOWLIST, onNoMatch=deny())
    other = _decision(rid=1, group="office", conditions=[_cond(value="JP")])
    ctx = {"ip": {"country": "US"}}

    as_shadow = matcher.match(
        [other, _decision(
            rid=2, group="office", status=RuleStatus.SHADOW,
            disposition=allow(), conditions=[_cond(value="US")],
        )],
        ctx, groups=[group],
    )
    # draft 规则根本不会下发到 Redis，等价于组内只有 rid=1
    as_absent = matcher.match([other], ctx, groups=[group])

    assert as_shadow.is_group_no_match == as_absent.is_group_no_match is True


# ---------- 求值器 fail-closed ----------
def test_evaluator_empty_conditions_never_match() -> None:
    ev = ConditionEvaluator()
    assert ev.evaluate_all([], {"ip": {"country": "CN"}}) is False
    assert ev.evaluate_any([], {"ip": {"country": "CN"}}) is False

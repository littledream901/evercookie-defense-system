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


# ---------- 求值器 fail-closed ----------
def test_evaluator_empty_conditions_never_match() -> None:
    ev = ConditionEvaluator()
    assert ev.evaluate_all([], {"ip": {"country": "CN"}}) is False
    assert ev.evaluate_any([], {"ip": {"country": "CN"}}) is False

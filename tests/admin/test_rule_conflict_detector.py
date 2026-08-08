"""规则冲突检测器的单元测试"""

import pytest

from fangyu_shared.schemas.disposition import Mechanism, Target, TargetKind, Verdict, allow, deny
from fangyu_shared.schemas.rule import DecisionRule, RuleCondition, RulePriority, RuleStatus

from src.domain.rule.conflict_detector import ConflictSeverity, RuleConflictDetector


def _rule(
    rid: int,
    name: str,
    priority: RulePriority,
    conditions: list[RuleCondition],
    status: RuleStatus = RuleStatus.PUBLISHED,
) -> DecisionRule:
    """创建测试用决策规则"""
    return DecisionRule(
        id=rid,
        siteId=0,
        name=name,
        status=status,
        priority=priority,
        conditions=conditions,
        disposition_match=deny(),
        disposition_miss=allow(),
        matchAll=True,
    )


def test_no_conflicts_when_single_rule():
    """单条规则时无冲突"""
    detector = RuleConflictDetector()
    rules = [_rule(1, "规则A", RulePriority.NORMAL, [RuleCondition(field="ip.country", op="eq", value="CN")])]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 0


def test_priority_override_conflict():
    """检测优先级覆盖冲突"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "高优先级拦截代理", RulePriority.CRITICAL,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)]
        ),
        _rule(
            2, "低优先级放行代理", RulePriority.NORMAL,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)]
        ),
    ]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 1
    assert conflicts[0].type == "priority_override"
    assert conflicts[0].severity == ConflictSeverity.HIGH
    assert 1 in conflicts[0].rule_ids
    assert 2 in conflicts[0].rule_ids


def test_priority_override_with_subset_conditions():
    """检测条件子集的优先级覆盖"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "拦截多国", RulePriority.HIGH,
            [RuleCondition(field="ip.country", op="in", value=["CN", "US", "JP"])]
        ),
        _rule(
            2, "放行中国", RulePriority.NORMAL,
            [RuleCondition(field="ip.country", op="eq", value="CN")]
        ),
    ]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 1
    assert conflicts[0].type == "priority_override"
    assert "规则 '放行中国'" in conflicts[0].message


def test_field_typo_detection():
    """检测字段拼写错误"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "错误字段", RulePriority.NORMAL,
            [RuleCondition(field="ip.is_proxy", op="eq", value=True)]  # 错误：应该是 ip.isProxy
        ),
    ]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 1
    assert conflicts[0].type == "field_typo"
    assert conflicts[0].severity == ConflictSeverity.MEDIUM
    assert "ip.is_proxy" in conflicts[0].message
    assert "ip.isProxy" in conflicts[0].message


def test_multiple_typos_in_one_rule():
    """一条规则中多个拼写错误"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "多个错误字段", RulePriority.NORMAL,
            [
                RuleCondition(field="ip.is_proxy", op="eq", value=True),
                RuleCondition(field="ip.is_vpn", op="eq", value=True),
            ]
        ),
    ]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 1
    assert "ip.is_proxy → ip.isProxy" in conflicts[0].message
    assert "ip.is_vpn → ip.isVpn" in conflicts[0].message


def test_no_conflict_for_draft_rules():
    """草稿状态的规则不参与冲突检测"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "已发布规则", RulePriority.CRITICAL,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)],
            status=RuleStatus.PUBLISHED
        ),
        _rule(
            2, "草稿规则", RulePriority.NORMAL,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)],
            status=RuleStatus.DRAFT
        ),
    ]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 0  # 草稿规则不参与检测


def test_format_conflicts_for_display():
    """测试格式化输出"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "规则A", RulePriority.CRITICAL,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)]
        ),
        _rule(
            2, "规则B", RulePriority.NORMAL,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)]
        ),
    ]
    
    conflicts = detector.detect(rules)
    formatted = detector.format_conflicts_for_display(conflicts)
    
    assert formatted["has_conflicts"] is True
    assert formatted["high_severity_count"] == 1
    assert len(formatted["conflicts"]) == 1
    assert formatted["conflicts"][0]["type"] == "priority_override"
    assert formatted["conflicts"][0]["severity"] == "high"
    assert "规则A" in formatted["conflicts"][0]["rule_names"]
    assert "规则B" in formatted["conflicts"][0]["rule_names"]


def test_no_conflicts_with_different_fields():
    """不同字段的规则不冲突"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "拦截代理", RulePriority.HIGH,
            [RuleCondition(field="ip.isProxy", op="eq", value=True)]
        ),
        _rule(
            2, "拦截中国", RulePriority.NORMAL,
            [RuleCondition(field="ip.country", op="eq", value="CN")]
        ),
    ]
    
    conflicts = detector.detect(rules)
    assert len(conflicts) == 0


def test_correct_camelcase_fields_no_conflict():
    """正确的 camelCase 字段名不报错"""
    detector = RuleConflictDetector()
    rules = [
        _rule(
            1, "正确字段", RulePriority.NORMAL,
            [
                RuleCondition(field="ip.isProxy", op="eq", value=True),
                RuleCondition(field="ip.country", op="eq", value="CN"),
            ]
        ),
    ]
    
    conflicts = detector.detect(rules)
    # 只检测拼写错误，不检测其他冲突
    typo_conflicts = [c for c in conflicts if c.type == "field_typo"]
    assert len(typo_conflicts) == 0

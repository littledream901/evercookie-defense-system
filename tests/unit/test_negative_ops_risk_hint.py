"""测试前端 NEGATIVE_OPS 集合与后端操作符行为的一致性。

目的：确保前端风险提示机制与后端实际行为匹配，避免误报或漏报。

规则：
- 在 NEGATIVE_OPS 中的操作符，在空值时必须返回 True（命中）
- 不在 NEGATIVE_OPS 中的操作符，在空值时应返回 False（不命中）
"""

import pytest
from fangyu_shared.rules.operators import apply_operator


# 前端 NEGATIVE_OPS 定义（手工同步自 dashboard-ui/src/constants/ruleFields.ts）
FRONTEND_NEGATIVE_OPS = frozenset([
    "neq",
    "not_in",
    "not_in_ci",
    "asn_not_in",
    "cidr_list_not_in",
])


@pytest.mark.parametrize(
    "op,expected_value",
    [
        ("neq", "CN"),
        ("not_in", ["CN", "US"]),
        ("not_in_ci", ["CN", "US"]),
        ("asn_not_in", [4134, 16509]),
        ("cidr_list_not_in", ["10.0.0.0/8", "192.168.0.0/16"]),
    ],
)
def test_negative_ops_match_on_null(op: str, expected_value: object) -> None:
    """NEGATIVE_OPS 中的操作符在空值时应该命中（返回 True）。
    
    这是「非白名单国家则拦截」这类规则的语义基础。
    """
    assert apply_operator(op, None, expected_value) is True, (
        f"操作符 {op} 在 NEGATIVE_OPS 中，但在空值时未命中（应返回 True）"
    )


@pytest.mark.parametrize(
    "op,expected_value",
    [
        ("eq", "CN"),
        ("in", ["CN", "US"]),
        ("in_ci", ["CN", "US"]),
        ("contains", "Beijing"),
        ("startswith", "CN"),
        ("endswith", ".com"),
        ("regex", "^CN"),
        ("gt", 80),
        ("gte", 80),
        ("lt", 20),
        ("lte", 20),
        ("cidr_in", "10.0.0.0/8"),
        ("cidr_list_in", ["10.0.0.0/8"]),
        ("asn_in", [4134]),
    ],
)
def test_positive_ops_do_not_match_on_null(op: str, expected_value: object) -> None:
    """正向操作符在空值时不应该命中（返回 False）。"""
    assert apply_operator(op, None, expected_value) is False, (
        f"正向操作符 {op} 在空值时错误命中（应返回 False）"
    )


def test_not_contains_does_not_match_on_null() -> None:
    """not_contains 在空值时不命中（返回 False）。
    
    这是特殊处理的操作符：虽然名字带 not_，但不属于 NEGATIVE_OPS。
    
    理由：防止运营把 not_contains 用在数值/布尔字段时条件恒成立，
    若处置是 deny 就等于对全部流量放开阻断。
    
    参见 operators.py:102-112 的实现注释。
    """
    assert apply_operator("not_contains", None, "test") is False
    assert apply_operator("not_contains", None, "Beijing") is False
    
    # 确认此操作符不在前端 NEGATIVE_OPS 集合中
    assert "not_contains" not in FRONTEND_NEGATIVE_OPS, (
        "not_contains 不应在 NEGATIVE_OPS 中，因为它在空值时不命中"
    )


def test_frontend_negative_ops_consistency() -> None:
    """验证前端 NEGATIVE_OPS 定义与后端行为一致。
    
    此测试失败意味着：
    1. 前端遗漏了某个在空值时会命中的操作符 → 缺少风险提示
    2. 前端包含了某个在空值时不会命中的操作符 → 误报风险提示
    """
    # 测试所有否定类操作符的空值行为
    all_negative_ops_candidates = [
        ("neq", "test"),
        ("not_in", ["test"]),
        ("not_in_ci", ["test"]),
        ("not_contains", "test"),
        ("asn_not_in", [4134]),
        ("cidr_list_not_in", ["10.0.0.0/8"]),
    ]
    
    actually_match_on_null = set()
    for op, value in all_negative_ops_candidates:
        if apply_operator(op, None, value):
            actually_match_on_null.add(op)
    
    # 验证前端定义与实际行为一致
    assert FRONTEND_NEGATIVE_OPS == actually_match_on_null, (
        f"前端 NEGATIVE_OPS 定义与后端行为不一致！\n"
        f"前端定义: {FRONTEND_NEGATIVE_OPS}\n"
        f"实际行为: {actually_match_on_null}\n"
        f"多余: {FRONTEND_NEGATIVE_OPS - actually_match_on_null}\n"
        f"遗漏: {actually_match_on_null - FRONTEND_NEGATIVE_OPS}"
    )


def test_risk_hint_logic_examples() -> None:
    """模拟前端风险提示逻辑的实际场景。"""
    
    # 场景1：ip.country 可能为空 + not_in_ci → 应该提示
    field_nullable = True
    operator = "not_in_ci"
    should_hint = field_nullable and operator in FRONTEND_NEGATIVE_OPS
    assert should_hint is True, "应该提示：空值时会命中，可能误杀"
    
    # 场景2：ip.city 可能为空 + not_contains → 不应该提示（已修复）
    field_nullable = True
    operator = "not_contains"
    should_hint = field_nullable and operator in FRONTEND_NEGATIVE_OPS
    assert should_hint is False, "不应该提示：not_contains 在空值时不命中"
    
    # 场景3：ip.isProxy 不为空 + neq → 不应该提示
    field_nullable = False
    operator = "neq"
    should_hint = field_nullable and operator in FRONTEND_NEGATIVE_OPS
    assert should_hint is False, "不应该提示：字段不可空"
    
    # 场景4：request.path 不为空 + contains → 不应该提示
    field_nullable = False
    operator = "contains"
    should_hint = field_nullable and operator in FRONTEND_NEGATIVE_OPS
    assert should_hint is False, "不应该提示：正向操作符"

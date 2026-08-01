"""条件表达式求值器。

替代 V1 中 evaluator.py 的 eval/字符串拼接实现，使用白名单式的操作符 dispatcher。

操作符实现统一放在 fangyu_shared.rules.operators，admin 的规则试跑接口复用同一份
逻辑，保证「后台预览命中」与「线上决策命中」结果一致。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.rules.operators import OPERATOR_NAMES, apply_operator, read_path
from fangyu_shared.schemas.rule import RuleCondition


class ConditionEvaluator:
    """按操作符白名单派发的条件求值器。"""

    __slots__ = ()

    @property
    def supported_ops(self) -> frozenset[str]:
        return OPERATOR_NAMES

    def evaluate(self, condition: RuleCondition, context: dict[str, Any]) -> bool:
        actual = read_path(context, condition.field)
        return apply_operator(condition.op, actual, condition.value)

    def evaluate_all(self, conditions: list[RuleCondition], context: dict[str, Any]) -> bool:
        if not conditions:
            # fail-closed：空条件不应命中全部流量。规则 schema 已强制
            # min_length=1，这里是第二道防线（例如手工构造的条件列表）。
            return False
        return all(self.evaluate(c, context) for c in conditions)

    def evaluate_any(self, conditions: list[RuleCondition], context: dict[str, Any]) -> bool:
        if not conditions:
            return False
        return any(self.evaluate(c, context) for c in conditions)

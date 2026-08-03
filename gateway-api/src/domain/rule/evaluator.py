"""条件表达式求值器。

替代 V1 中 evaluator.py 的 eval/字符串拼接实现，使用白名单式的操作符 dispatcher。

操作符实现统一放在 fangyu_shared.rules.operators，admin 的规则试跑接口复用同一份
逻辑，保证「后台预览命中」与「线上决策命中」结果一致。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.rules.operators import (
    OPERATOR_NAMES,
    evaluate_condition,
    evaluate_conditions,
)
from fangyu_shared.schemas.rule import RuleCondition


class ConditionEvaluator:
    """条件求值器。

    组合逻辑与单条求值全部委托给 fangyu_shared.rules.operators，本类只做
    领域层的薄封装。admin 的规则试跑调用同一组函数，因此「后台预览命中」
    与「线上决策命中」不可能出现分歧。
    """

    __slots__ = ()

    @property
    def supported_ops(self) -> frozenset[str]:
        return OPERATOR_NAMES

    def evaluate(self, condition: RuleCondition, context: dict[str, Any]) -> bool:
        return evaluate_condition(condition, context)

    def evaluate_all(self, conditions: list[RuleCondition], context: dict[str, Any]) -> bool:
        return evaluate_conditions(conditions, context, match_all=True)

    def evaluate_any(self, conditions: list[RuleCondition], context: dict[str, Any]) -> bool:
        return evaluate_conditions(conditions, context, match_all=False)

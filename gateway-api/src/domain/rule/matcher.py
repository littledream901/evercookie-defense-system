"""决策规则匹配器。

职责
----
- 按优先级遍历已发布的决策规则，首个命中即终止
- allowlist 规则组全部未命中时，施加该组的 ``on_no_match``
- SHADOW 状态规则参与求值但**不影响结果**，仅记录命中，供发布前测算影响面
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fangyu_shared.schemas.rule import (
    DecisionRule,
    GroupMode,
    RuleGroup,
    RulePriority,
)

from src.domain.rule.evaluator import ConditionEvaluator

_PRIORITY_ORDER: dict[RulePriority, int] = {
    RulePriority.CRITICAL: 0,
    RulePriority.HIGH: 1,
    RulePriority.NORMAL: 2,
    RulePriority.LOW: 3,
}


@dataclass(frozen=True, slots=True)
class ShadowMatch:
    rule: DecisionRule


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: bool
    rule: DecisionRule | None = None
    group: RuleGroup | None = None
    """命中 allowlist 组的 on_no_match 时填充，此时 rule 为 None。"""
    shadow_matches: tuple[ShadowMatch, ...] = field(default=())

    @property
    def is_group_no_match(self) -> bool:
        return self.rule is None and self.group is not None


class DecisionRuleMatcher:
    """决策规则匹配器。"""

    def __init__(self, evaluator: ConditionEvaluator | None = None) -> None:
        self._evaluator = evaluator or ConditionEvaluator()

    def match(
        self,
        rules: list[DecisionRule],
        context: dict[str, Any],
        *,
        groups: list[RuleGroup] | None = None,
    ) -> MatchResult:
        shadow: list[ShadowMatch] = []
        winner: DecisionRule | None = None

        for rule in self._sort(rules):
            if not (rule.is_active or rule.is_shadow):
                continue
            if not self._hits(rule, context):
                continue
            if rule.is_shadow:
                shadow.append(ShadowMatch(rule=rule))
                continue
            if winner is None:
                winner = rule
                # 不能提前 break：影子规则仍需继续评估以完整记录影响面

        if winner is not None:
            return MatchResult(matched=True, rule=winner, shadow_matches=tuple(shadow))

        group = self._unmatched_allowlist(rules, context, groups or [])
        if group is not None:
            return MatchResult(matched=True, group=group, shadow_matches=tuple(shadow))

        return MatchResult(matched=False, shadow_matches=tuple(shadow))

    def _hits(self, rule: DecisionRule, context: dict[str, Any]) -> bool:
        if rule.match_all:
            return self._evaluator.evaluate_all(rule.conditions, context)
        return self._evaluator.evaluate_any(rule.conditions, context)

    def _unmatched_allowlist(
        self,
        rules: list[DecisionRule],
        context: dict[str, Any],
        groups: list[RuleGroup],
    ) -> RuleGroup | None:
        """找出「组内白名单规则全未命中」的 allowlist 组。

        作用域严格限制在组内：只考察 ``rule.group == group.name`` 的规则，
        避免旧版 on_miss 全局遍历导致「新增无关规则改变全站默认处置」。
        """
        ordered_groups = sorted(
            (g for g in groups if g.enabled and g.mode == GroupMode.ALLOWLIST),
            key=lambda g: _PRIORITY_ORDER.get(g.priority, 99),
        )
        for group in ordered_groups:
            members = [r for r in rules if r.group == group.name and r.is_active]
            if not members:
                # 空白名单组不生效：否则一个刚建好还没加规则的组会拦下全部流量
                continue
            if any(self._hits(r, context) for r in members):
                continue
            return group
        return None

    @staticmethod
    def _sort(rules: list[DecisionRule]) -> list[DecisionRule]:
        return sorted(
            rules,
            key=lambda r: (_PRIORITY_ORDER.get(r.priority, 99), r.id or 0),
        )

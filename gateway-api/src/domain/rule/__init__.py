"""规则领域模型。"""

from __future__ import annotations

from src.domain.rule.evaluator import ConditionEvaluator
from src.domain.rule.matcher import DecisionRuleMatcher, MatchResult, ShadowMatch

__all__ = ["ConditionEvaluator", "DecisionRuleMatcher", "MatchResult", "ShadowMatch"]

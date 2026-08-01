"""规则试跑接口：在不上线的情况下评估规则命中情况。

安全模型：
- 本接口会暴露规则的命中逻辑与处置结果，未鉴权将允许攻击者反复试探
  规则边界，从而反推出绕过策略。因此与 ``/decide`` 同级保护。
- 由 :class:`AppKeyEnforcementMiddleware` 在 body 解析前拦截，
  路由层再通过 :func:`require_app_key` 依赖取解析结果做二次确认。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from fangyu_shared.schemas.common import BaseSchema, SuccessResponse
from fangyu_shared.schemas.disposition import Mechanism, Verdict
from fangyu_shared.schemas.rule import DecisionRule

from src.domain.rule.evaluator import ConditionEvaluator
from src.domain.rule.matcher import DecisionRuleMatcher
from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key

router = APIRouter(tags=["rule"])


class RuleTestRequest(BaseSchema):
    rule: DecisionRule
    context: dict[str, Any] = Field(default_factory=dict)


class RuleTestResponse(BaseSchema):
    matched: bool
    rule_id: int | None = Field(default=None, alias="ruleId")
    verdict: Verdict | None = None
    mechanism: Mechanism | None = None


@router.post(
    "/rule/test",
    response_model=SuccessResponse[RuleTestResponse],
    summary="规则试跑",
)
async def rule_test(
    payload: RuleTestRequest,
    _resolved: ResolvedAppKey = Depends(require_app_key),
) -> SuccessResponse[RuleTestResponse]:
    matcher = DecisionRuleMatcher(ConditionEvaluator())
    result = matcher.match([payload.rule], payload.context)
    rule = result.rule
    data = RuleTestResponse(
        matched=rule is not None,
        ruleId=rule.id if rule else None,
        verdict=rule.disposition.verdict if rule else None,
        mechanism=rule.disposition.mechanism if rule else None,
    )
    return SuccessResponse[RuleTestResponse](data=data)

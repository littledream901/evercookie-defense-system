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
from src.infrastructure.rule_repo.rule_repository import RuleRepository
from src.interfaces.http.dependencies import get_decision_service
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
    # 必须走 effective_match_disposition：新式规则只传 disposition_match，
    # 直接读 rule.disposition 会是 None 并抛 AttributeError。
    disposition = rule.effective_match_disposition if rule else None
    data = RuleTestResponse(
        matched=rule is not None,
        ruleId=rule.id if rule else None,
        verdict=disposition.verdict if disposition else None,
        mechanism=disposition.mechanism if disposition else None,
    )
    return SuccessResponse[RuleTestResponse](data=data)


@router.get(
    "/rules/debug",
    summary="调试：读取站点当前缓存的决策规则",
)
async def list_rules_debug(
    resolved: ResolvedAppKey = Depends(require_app_key),
    svc=Depends(get_decision_service),
) -> SuccessResponse[dict]:
    repo: RuleRepository = svc._deps.rule_repository
    rule_set = await repo.get_rule_set(resolved.app_id)
    rules = []
    for r in rule_set.decision_rules:
        rules.append({
            "id": r.id,
            "name": r.name,
            "status": r.status.value,
            "matchAll": r.match_all,
            "conditions": [{"field": c.field, "op": c.op, "value": c.value} for c in r.conditions],
            "disposition": {
                "verdict": r.effective_match_disposition.verdict.value,
                "mechanism": r.effective_match_disposition.mechanism.value,
            },
        })
    return SuccessResponse(data={"appId": resolved.app_id, "total": len(rules), "rules": rules})

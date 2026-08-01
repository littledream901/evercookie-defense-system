from __future__ import annotations

import pytest
from pydantic import ValidationError

from fangyu_shared.schemas.disposition import Mechanism, Verdict, deny
from fangyu_shared.schemas.rule import (
    DecisionRule,
    RuleCondition,
    RuleKind,
    RulePriority,
    RuleStatus,
)

from src.interfaces.http.v2.rule_templates import (
    RulePreviewRequest,
    list_rule_templates,
    preview_rule,
)


def _rule(**overrides) -> DecisionRule:
    payload = {
        "id": 1,
        "appId": 1,
        "name": "cn-block",
        "description": "",
        "status": RuleStatus.DRAFT,
        "priority": RulePriority.HIGH,
        "conditions": [RuleCondition(field="ip.country", op="in", value=["CN"])],
        "disposition": deny(),
        "version": 1,
        "tags": [],
    }
    payload.update(overrides)
    return DecisionRule(**payload)


@pytest.mark.asyncio
async def test_rule_templates_returns_builtin_items():
    resp = await list_rule_templates()
    assert resp.data is not None
    assert len(resp.data) >= 1
    assert any(item.id == "block-country" for item in resp.data)


@pytest.mark.asyncio
async def test_templates_carry_structured_disposition():
    resp = await list_rule_templates()
    tpl = next(t for t in resp.data if t.id == "block-country")
    assert tpl.kind == RuleKind.DECISION
    assert tpl.disposition is not None
    assert tpl.disposition.verdict == Verdict.HOSTILE
    # 决策模板不携带 weight（命中即终止，权重无意义）
    assert tpl.weight is None


@pytest.mark.asyncio
async def test_scoring_template_carries_weight_not_disposition():
    resp = await list_rule_templates()
    tpl = next(t for t in resp.data if t.kind == RuleKind.SCORING)
    assert tpl.weight is not None
    assert tpl.disposition is None


@pytest.mark.asyncio
async def test_redirect_template_has_target_url():
    resp = await list_rule_templates()
    tpl = next(t for t in resp.data if t.id == "redirect-suspect-region")
    assert tpl.disposition is not None
    assert tpl.disposition.mechanism == Mechanism.REDIRECT
    assert tpl.disposition.target.url is not None


@pytest.mark.asyncio
async def test_rule_preview_matches_country_condition():
    payload = RulePreviewRequest(rule=_rule(), context={"ip": {"country": "CN"}})
    resp = await preview_rule(payload)
    assert resp.data is not None
    assert resp.data.matched is True
    assert resp.data.verdict == Verdict.HOSTILE
    assert resp.data.mechanism == Mechanism.DENY
    assert resp.data.http_status == 403
    assert resp.data.conditions[0].matched is True


@pytest.mark.asyncio
async def test_rule_preview_miss_returns_no_disposition():
    payload = RulePreviewRequest(rule=_rule(), context={"ip": {"country": "US"}})
    resp = await preview_rule(payload)
    assert resp.data.matched is False
    assert resp.data.verdict is None
    assert resp.data.mechanism is None


@pytest.mark.asyncio
async def test_rule_preview_parses_user_agent():
    rule = _rule(
        conditions=[RuleCondition(field="ua.crawler_category", op="eq", value="search_engine")]
    )
    payload = RulePreviewRequest(
        rule=rule,
        userAgent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    )
    resp = await preview_rule(payload)
    assert resp.data.matched is True
    # 上下文应回传解析结果，供前端展示
    assert resp.data.context["ua"]["is_bot"] is True


@pytest.mark.asyncio
async def test_rule_preview_respects_match_any():
    rule = _rule(
        matchAll=False,
        conditions=[
            RuleCondition(field="ip.country", op="in", value=["CN"]),
            RuleCondition(field="ip.country", op="in", value=["RU"]),
        ],
    )
    payload = RulePreviewRequest(rule=rule, context={"ip": {"country": "RU"}})
    resp = await preview_rule(payload)
    assert resp.data.matched is True


def test_empty_conditions_rejected_at_schema_level():
    # fail-closed：空条件规则不得存在，否则会命中全部流量
    with pytest.raises(ValidationError):
        _rule(conditions=[])


def test_unknown_field_namespace_rejected():
    with pytest.raises(ValidationError):
        _rule(conditions=[RuleCondition(field="country", op="in", value=["CN"])])

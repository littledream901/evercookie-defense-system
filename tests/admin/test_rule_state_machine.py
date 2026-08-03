"""规则状态机单元测试。"""
from __future__ import annotations

import pytest

from fangyu_shared.exceptions import ValidationException
from fangyu_shared.schemas.rule import RuleStatus
from src.domain.rule.state_machine import RuleStateMachine


class TestRuleStateMachine:
    @pytest.mark.parametrize(
        "src, dst",
        [
            (RuleStatus.DRAFT, RuleStatus.PUBLISHED),
            (RuleStatus.DRAFT, RuleStatus.ARCHIVED),
            (RuleStatus.DRAFT, RuleStatus.DISABLED),
            (RuleStatus.PUBLISHED, RuleStatus.DISABLED),
            (RuleStatus.PUBLISHED, RuleStatus.ARCHIVED),
            (RuleStatus.DISABLED, RuleStatus.PUBLISHED),
            (RuleStatus.DISABLED, RuleStatus.ARCHIVED),
            (RuleStatus.ARCHIVED, RuleStatus.DRAFT),  # 恢复编辑
        ],
    )
    def test_allowed(self, src: RuleStatus, dst: RuleStatus):
        assert RuleStateMachine.can_transition(src, dst)
        RuleStateMachine.ensure_transition(src, dst)  # 不抛异常

    @pytest.mark.parametrize(
        "src, dst",
        [
            (RuleStatus.PUBLISHED, RuleStatus.DRAFT),
            (RuleStatus.ARCHIVED, RuleStatus.PUBLISHED),
            (RuleStatus.ARCHIVED, RuleStatus.DISABLED),
        ],
    )
    def test_forbidden(self, src: RuleStatus, dst: RuleStatus):
        assert not RuleStateMachine.can_transition(src, dst)
        with pytest.raises(ValidationException) as excinfo:
            RuleStateMachine.ensure_transition(src, dst)
        assert excinfo.value.details["current"] == src.value
        assert excinfo.value.details["target"] == dst.value

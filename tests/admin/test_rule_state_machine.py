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
            (RuleStatus.DRAFT, RuleStatus.SHADOW),  # 进入影子观察
            (RuleStatus.SHADOW, RuleStatus.PUBLISHED),  # 影子数据合格，正式上线
            (RuleStatus.SHADOW, RuleStatus.DRAFT),  # 观察发现问题，退回修改
            (RuleStatus.SHADOW, RuleStatus.ARCHIVED),  # 直接放弃
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
            # 已生效规则不得静默降级为「仅观察」：管理员会以为拦截还在跑
            (RuleStatus.PUBLISHED, RuleStatus.SHADOW),
            # disabled 与 shadow 都是「不参与真实处置」，语义重叠无意义
            (RuleStatus.DISABLED, RuleStatus.SHADOW),
            (RuleStatus.ARCHIVED, RuleStatus.SHADOW),
            (RuleStatus.SHADOW, RuleStatus.DISABLED),
        ],
    )
    def test_forbidden(self, src: RuleStatus, dst: RuleStatus):
        assert not RuleStateMachine.can_transition(src, dst)
        with pytest.raises(ValidationException) as excinfo:
            RuleStateMachine.ensure_transition(src, dst)
        assert excinfo.value.details["current"] == src.value
        assert excinfo.value.details["target"] == dst.value

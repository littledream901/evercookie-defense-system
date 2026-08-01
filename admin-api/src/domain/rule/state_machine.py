"""规则发布状态机。

- draft -> published (审核通过时)
- published -> disabled (人工下线)
- disabled -> published (重新启用)
- 任意 -> archived (归档)
"""

from __future__ import annotations

from fangyu_shared.exceptions import ValidationException
from fangyu_shared.schemas.rule import RuleStatus

_TRANSITIONS: dict[RuleStatus, set[RuleStatus]] = {
    RuleStatus.DRAFT: {RuleStatus.PUBLISHED, RuleStatus.ARCHIVED, RuleStatus.DISABLED},
    RuleStatus.PUBLISHED: {RuleStatus.DISABLED, RuleStatus.ARCHIVED},
    RuleStatus.DISABLED: {RuleStatus.PUBLISHED, RuleStatus.ARCHIVED},
    RuleStatus.ARCHIVED: set(),
}


class RuleStateMachine:
    @staticmethod
    def can_transition(current: RuleStatus, target: RuleStatus) -> bool:
        return target in _TRANSITIONS.get(current, set())

    @staticmethod
    def ensure_transition(current: RuleStatus, target: RuleStatus) -> None:
        if not RuleStateMachine.can_transition(current, target):
            raise ValidationException(
                f"规则状态不允许由 {current.value} 变更为 {target.value}",
                details={"current": current.value, "target": target.value},
            )

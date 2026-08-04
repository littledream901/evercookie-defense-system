"""规则发布状态机。

- draft -> published (审核通过时)
- draft -> shadow   (进入影子测试，先观察命中影响面再决定是否发布)
- shadow -> published (影子测试通过，正式上线)
- shadow -> draft    (测试发现问题，退回草稿修改)
- shadow -> archived (直接放弃，不再编辑)
- published -> disabled (人工下线)
- disabled -> published (重新启用)
- disabled -> archived (归档下线)
- 任意 -> archived (归档)
- archived -> draft (恢复编辑)

故意不允许 published → shadow：已生效规则悄悄变成"仅观察"会让管理员
误以为拦截仍在运行；要测试变更应先 disable → 编辑 → to_shadow。
也不允许 disabled → shadow：两者都是"不生效"状态，语义重叠无实际价值。
"""

from __future__ import annotations

from fangyu_shared.exceptions import ValidationException
from fangyu_shared.schemas.rule import RuleStatus

SYNCABLE_STATUSES: frozenset[RuleStatus] = frozenset(
    {RuleStatus.PUBLISHED, RuleStatus.SHADOW}
)
"""会被下发到 gateway（Redis 规则分片）的状态集合。

放在领域层而不是各自散落在缓存/仓储/服务里：这三处若不一致，就会出现
「SQL 查出来了但缓存过滤掉」这类静默失效——影子模式此前正是这样成为死代码的。
SHADOW 参与下发但不参与真实处置，该保证由 gateway 匹配器的 is_shadow 分支负责。
"""

_TRANSITIONS: dict[RuleStatus, set[RuleStatus]] = {
    RuleStatus.DRAFT: {RuleStatus.PUBLISHED, RuleStatus.ARCHIVED, RuleStatus.DISABLED, RuleStatus.SHADOW},
    RuleStatus.SHADOW: {RuleStatus.PUBLISHED, RuleStatus.DRAFT, RuleStatus.ARCHIVED},
    RuleStatus.PUBLISHED: {RuleStatus.DISABLED, RuleStatus.ARCHIVED},
    RuleStatus.DISABLED: {RuleStatus.PUBLISHED, RuleStatus.ARCHIVED},
    RuleStatus.ARCHIVED: {RuleStatus.DRAFT},
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

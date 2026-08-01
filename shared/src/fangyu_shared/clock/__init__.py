"""Clock：频控窗口、封禁阈值与行为时序的领域词汇。

本包只含**枚举、常量与纯函数**，不依赖 pydantic、不导入
``fangyu_shared.schemas``、不含 Redis 访问：

- wire 契约（``BehaviorEvent`` / ``ClockLimits``）在
  :mod:`fangyu_shared.schemas.clock`
- 存储实现在 gateway 侧 ``src.infrastructure.clock``

这样分层同时解决两个问题：``schemas.decision`` 可以安全引用行为事件而不形成
循环导入；admin-api 复用同一套键构造与窗口定义读取监控数据，避免旧版
gateway 与 admin 各硬编码一份窗口常量、改一边不同步的问题。
"""

from __future__ import annotations

from fangyu_shared.clock.behavior import (
    MAX_CLIENT_SKEW_MS,
    BehaviorKind,
    make_member,
    normalize_event_time,
)
from fangyu_shared.clock.limits import (
    DEFAULT_BAN_SECONDS,
    DEFAULT_LIMITS,
    MAX_BAN_SECONDS,
)
from fangyu_shared.clock.windows import (
    ALL_WINDOWS,
    BEHAVIOR_MAX_SEQUENCE,
    BEHAVIOR_RETENTION_SECONDS,
    MAX_BEHAVIOR_EVENTS_PER_REQUEST,
    RETENTION_SECONDS,
    WINDOW_BURST,
    WINDOW_HOUR,
    WINDOW_SHORT,
    ClockDimension,
    ClockWindow,
    ban_key,
    behavior_key,
    limits_key,
    rate_key,
)

__all__ = [
    "ALL_WINDOWS",
    "BEHAVIOR_MAX_SEQUENCE",
    "BEHAVIOR_RETENTION_SECONDS",
    "DEFAULT_BAN_SECONDS",
    "DEFAULT_LIMITS",
    "MAX_BAN_SECONDS",
    "MAX_BEHAVIOR_EVENTS_PER_REQUEST",
    "MAX_CLIENT_SKEW_MS",
    "RETENTION_SECONDS",
    "WINDOW_BURST",
    "WINDOW_HOUR",
    "WINDOW_SHORT",
    "BehaviorKind",
    "ClockDimension",
    "ClockWindow",
    "ban_key",
    "behavior_key",
    "limits_key",
    "make_member",
    "normalize_event_time",
    "rate_key",
]

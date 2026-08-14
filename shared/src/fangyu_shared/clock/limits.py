"""频控阈值的默认值与边界。

wire 契约 :class:`fangyu_shared.schemas.clock.ClockLimits` 放在 schemas 侧，
本模块只放纯常量——见 :mod:`fangyu_shared.clock.behavior` 的分层说明。
"""

from __future__ import annotations

DEFAULT_LIMITS: dict[str, int] = {
    "burst": 1000,
    "short": 10000,
    "hour": 100000,
}
"""默认阈值：窗口名 → 允许次数。

取值极宽松是有意的：频控是最容易造成大面积误伤的手段，未显式配置时应近乎禁用。
只挡住极端异常流量（如 DDoS），正常业务流量绝不会触发。站点需要精细频控时
必须在后台显式配置阈值，而不是依赖这个全局默认值。
"""

DEFAULT_BAN_SECONDS = 900
"""默认封禁时长 15 分钟。"""

MAX_BAN_SECONDS = 86400
"""封禁时长上限 24 小时。超过一天的封禁应该走人工黑名单，而非自动频控。"""

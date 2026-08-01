"""频控阈值的默认值与边界。

wire 契约 :class:`fangyu_shared.schemas.clock.ClockLimits` 放在 schemas 侧，
本模块只放纯常量——见 :mod:`fangyu_shared.clock.behavior` 的分层说明。
"""

from __future__ import annotations

DEFAULT_LIMITS: dict[str, int] = {
    "burst": 30,
    "short": 120,
    "hour": 3000,
}
"""默认阈值：窗口名 → 允许次数。

取值偏宽松是有意的：频控是最容易造成大面积误伤的手段，默认值应该只挡住
明显异常的流量，精细收紧交给站点自行配置。
"""

DEFAULT_BAN_SECONDS = 900
"""默认封禁时长 15 分钟。"""

MAX_BAN_SECONDS = 86400
"""封禁时长上限 24 小时。超过一天的封禁应该走人工黑名单，而非自动频控。"""

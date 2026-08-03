"""Clock 的 wire 契约：行为事件与频控阈值。

领域词汇（枚举、窗口、纯函数）在 :mod:`fangyu_shared.clock`，本模块只负责
pydantic 形状。这样分层是为了让 ``clock`` 包不依赖 schemas，避免
``schemas.decision`` 引用行为事件时形成循环导入。
"""

from __future__ import annotations

from pydantic import Field, model_validator

from fangyu_shared.clock.behavior import BehaviorKind
from fangyu_shared.clock.limits import (
    DEFAULT_BAN_SECONDS,
    DEFAULT_LIMITS,
    MAX_BAN_SECONDS,
)
from fangyu_shared.clock.windows import ALL_WINDOWS, ClockWindow
from fangyu_shared.schemas.common import BaseSchema


class BehaviorEvent(BaseSchema):
    """单条行为事件。

    ``client_ts_ms``
        客户端事件发生时间（毫秒）。仅作为排序依据的**原始输入**，最终
        落库的 score 是归一化后的值，见
        :func:`fangyu_shared.clock.behavior.normalize_event_time`。
    ``data``
        类型相关的补充数据（如坐标、键码类别）。刻意保持自由形态——采集端
        演进快，强约束会导致每次采集升级都要改网关 schema。
    """

    kind: BehaviorKind
    client_ts_ms: int = Field(..., alias="clientTsMs", ge=0)
    data: dict[str, float | int | str | bool] = Field(default_factory=dict)


class ClockLimits(BaseSchema):
    """某个 app 的频控阈值。

    ``windows`` 缺省的窗口自动回退到
    :data:`fangyu_shared.clock.limits.DEFAULT_LIMITS`，因此站点只需覆盖
    关心的那一档。
    """

    app_id: int = Field(..., alias="appId", ge=0)
    """站点 ID。``0`` 表示全局阈值（不绑定具体站点）。"""
    enabled: bool = True
    windows: dict[str, int] = Field(default_factory=dict)
    ban_seconds: int = Field(
        default=DEFAULT_BAN_SECONDS, alias="banSeconds", ge=0, le=MAX_BAN_SECONDS
    )
    ban_enabled: bool = Field(default=True, alias="banEnabled")
    """超限后是否升级为封禁。关闭则只拒绝当次请求，不留封禁状态。"""

    @model_validator(mode="after")
    def _check_window_names(self) -> ClockLimits:
        known = {w.name for w in ALL_WINDOWS}
        unknown = set(self.windows) - known
        if unknown:
            raise ValueError(f"未知的频控窗口: {sorted(unknown)}（允许 {sorted(known)}）")
        for name, limit in self.windows.items():
            if limit < 0:
                raise ValueError(f"频控阈值不能为负: {name}={limit}")
        return self

    def limit_for(self, window: ClockWindow) -> int:
        """取某窗口的阈值。0 表示该窗口不限流。"""
        return self.windows.get(window.name, DEFAULT_LIMITS.get(window.name, 0))


def default_limits(app_id: int) -> ClockLimits:
    """未配置站点阈值时使用的默认值。"""
    return ClockLimits(appId=app_id)

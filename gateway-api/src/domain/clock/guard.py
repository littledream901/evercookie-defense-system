"""频控判定。

职责边界
--------
本模块**只做判定**，不碰 Redis。计数由 :class:`ClockRepository` 读来，阈值由
:class:`ClockLimits` 提供，判定是纯函数，可完整单测——旧版的
``check_over_limit`` 混杂了阈值读取与比较，测一次判定要先起 Redis。

只判定不重复检查
----------------
旧版同一请求会对同一 IP 调 ``check_over_limit`` 两次、``check_ip`` 两次：一次
在接口层快速拦截，一次在流水线 ``native`` 阶段。因为前者命中即 return，后者的
对应分支成了不可达代码。本实现只在流水线的 CLOCK 阶段判定一次。
"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.clock.windows import ALL_WINDOWS, ClockDimension
from fangyu_shared.schemas.clock import ClockLimits

from src.infrastructure.clock.repository import ClockReading, DimensionCounts


@dataclass(frozen=True, slots=True)
class LimitBreach:
    """一次阈值突破。"""

    dimension: ClockDimension
    window_name: str
    count: int
    limit: int

    @property
    def reason(self) -> str:
        return (
            f"rate_limit:{self.dimension.value}:{self.window_name}"
            f"({self.count}/{self.limit})"
        )


@dataclass(frozen=True, slots=True)
class ClockVerdict:
    """Clock 阶段结论。"""

    ban_reason: str | None = None
    breach: LimitBreach | None = None

    @property
    def is_banned(self) -> bool:
        return self.ban_reason is not None

    @property
    def is_over_limit(self) -> bool:
        return self.breach is not None

    @property
    def blocked(self) -> bool:
        return self.is_banned or self.is_over_limit


class ClockGuard:
    """频控判定器。"""

    def evaluate(self, reading: ClockReading, limits: ClockLimits) -> ClockVerdict:
        """判定本次请求是否应被频控拦截。

        判定顺序：先看封禁（已成事实），再看窗口阈值。窗口按宽度升序遍历，
        窄窗口先命中，超限原因里报告的就是最先突破的那一档。
        """
        if not limits.enabled:
            return ClockVerdict()

        ban = reading.active_ban
        if ban is not None:
            dimension, state = ban
            reason = state.reason or "banned"
            return ClockVerdict(ban_reason=f"ban:{dimension.value}:{reason}")

        for counts in (reading.ip, reading.fingerprint):
            breach = self._check_dimension(counts, limits)
            if breach is not None:
                return ClockVerdict(breach=breach)

        return ClockVerdict()

    @staticmethod
    def _check_dimension(
        counts: DimensionCounts, limits: ClockLimits
    ) -> LimitBreach | None:
        for window in ALL_WINDOWS:
            limit = limits.limit_for(window)
            if limit <= 0:
                # 0 表示该窗口不限流
                continue
            count = counts.count_for(window.name)
            if count > limit:
                return LimitBreach(
                    dimension=counts.dimension,
                    window_name=window.name,
                    count=count,
                    limit=limit,
                )
        return None

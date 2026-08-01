"""Clock 领域逻辑：频控判定。"""

from __future__ import annotations

from src.domain.clock.guard import ClockGuard, ClockVerdict, LimitBreach

__all__ = ["ClockGuard", "ClockVerdict", "LimitBreach"]

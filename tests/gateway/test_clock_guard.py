"""频控判定测试。

判定是纯函数，不需要 Redis——这是把判定与存储分离的直接收益。旧版
``check_over_limit`` 内部读阈值，测一次判定要先起 Redis。
"""

from __future__ import annotations

import pytest
from fangyu_shared.clock.windows import (
    ALL_WINDOWS,
    WINDOW_BURST,
    WINDOW_HOUR,
    WINDOW_SHORT,
    ClockDimension,
)
from fangyu_shared.schemas.clock import ClockLimits
from src.domain.clock.guard import ClockGuard
from src.infrastructure.clock.repository import BanState, ClockReading, DimensionCounts


def _counts(
    dimension: ClockDimension,
    *,
    burst: int = 0,
    short: int = 0,
    hour: int = 0,
    ban: BanState | None = None,
) -> DimensionCounts:
    return DimensionCounts(
        dimension=dimension,
        value="v",
        counts={"burst": burst, "short": short, "hour": hour},
        ban=ban or BanState(banned=False),
    )


def _reading(
    *,
    ip: DimensionCounts | None = None,
    fp: DimensionCounts | None = None,
) -> ClockReading:
    return ClockReading(
        ip=ip or _counts(ClockDimension.IP),
        fingerprint=fp or _counts(ClockDimension.FINGERPRINT),
        now_ms=1_700_000_000_000,
    )


def _limits(**kwargs: int) -> ClockLimits:
    return ClockLimits(siteId=1, windows=dict(kwargs) or {"burst": 10})


# ---------- 窗口语义 ----------
def test_window_names_match_declared_seconds() -> None:
    """窗口名与秒数在同一对象里成对声明，不会出现旧版名实不符的情况。"""
    assert WINDOW_BURST.seconds == 10
    assert WINDOW_SHORT.seconds == 60
    assert WINDOW_HOUR.seconds == 3600


def test_windows_sorted_ascending() -> None:
    """判定按宽度升序遍历，窄窗口先命中。"""
    widths = [w.seconds for w in ALL_WINDOWS]
    assert widths == sorted(widths)


def test_zero_width_window_rejected() -> None:
    from fangyu_shared.clock.windows import ClockWindow

    with pytest.raises(ValueError, match="窗口宽度必须为正"):
        ClockWindow("bad", 0)


# ---------- 阈值判定 ----------
def test_under_limit_passes() -> None:
    verdict = ClockGuard().evaluate(
        _reading(ip=_counts(ClockDimension.IP, burst=5)), _limits(burst=10)
    )
    assert verdict.blocked is False


def test_equal_to_limit_passes() -> None:
    """等于阈值不算超限，用严格大于比较。"""
    verdict = ClockGuard().evaluate(
        _reading(ip=_counts(ClockDimension.IP, burst=10)), _limits(burst=10)
    )
    assert verdict.blocked is False


def test_over_limit_blocks() -> None:
    verdict = ClockGuard().evaluate(
        _reading(ip=_counts(ClockDimension.IP, burst=11)), _limits(burst=10)
    )
    assert verdict.is_over_limit is True
    assert verdict.breach is not None
    assert verdict.breach.window_name == "burst"
    assert verdict.breach.dimension == ClockDimension.IP


def test_narrowest_window_reported_first() -> None:
    """burst 与 short 同时超限时，报告 burst——它更能说明是脚本行为。"""
    verdict = ClockGuard().evaluate(
        _reading(ip=_counts(ClockDimension.IP, burst=99, short=999)),
        _limits(burst=10, short=100),
    )
    assert verdict.breach is not None
    assert verdict.breach.window_name == "burst"


def test_zero_limit_means_unlimited() -> None:
    """阈值 0 表示该窗口不限流，不是「一次都不许」。"""
    verdict = ClockGuard().evaluate(
        _reading(ip=_counts(ClockDimension.IP, burst=99999)), _limits(burst=0)
    )
    assert verdict.blocked is False


def test_fingerprint_dimension_also_enforced() -> None:
    """指纹维度独立限流：换 IP 不能绕过。

    旧版填充了 finger_60s_count 却从不参与判定，指纹维度实际只在最窄窗口生效。
    """
    verdict = ClockGuard().evaluate(
        _reading(fp=_counts(ClockDimension.FINGERPRINT, short=200)),
        _limits(short=100),
    )
    assert verdict.is_over_limit is True
    assert verdict.breach is not None
    assert verdict.breach.dimension == ClockDimension.FINGERPRINT


def test_disabled_limits_skip_all_checks() -> None:
    limits = ClockLimits(siteId=1, enabled=False, windows={"burst": 1})
    verdict = ClockGuard().evaluate(
        _reading(ip=_counts(ClockDimension.IP, burst=9999)), limits
    )
    assert verdict.blocked is False


# ---------- 封禁优先 ----------
def test_ban_takes_precedence_over_counts() -> None:
    banned = _counts(
        ClockDimension.IP, burst=0, ban=BanState(banned=True, reason="rate_limit:ip:burst")
    )
    verdict = ClockGuard().evaluate(_reading(ip=banned), _limits(burst=10))
    assert verdict.is_banned is True
    assert verdict.is_over_limit is False
    assert "rate_limit:ip:burst" in (verdict.ban_reason or "")


def test_ip_ban_reported_before_fingerprint_ban() -> None:
    verdict = ClockGuard().evaluate(
        _reading(
            ip=_counts(ClockDimension.IP, ban=BanState(banned=True, reason="ip_reason")),
            fp=_counts(
                ClockDimension.FINGERPRINT, ban=BanState(banned=True, reason="fp_reason")
            ),
        ),
        _limits(burst=10),
    )
    assert "ip_reason" in (verdict.ban_reason or "")


# ---------- 阈值配置校验 ----------
def test_unknown_window_name_rejected() -> None:
    """阈值键必须是已声明的窗口名，防止配错了却静默不生效。"""
    with pytest.raises(ValueError, match="未知的频控窗口"):
        ClockLimits(siteId=1, windows={"minute": 100})


def test_negative_limit_rejected() -> None:
    with pytest.raises(ValueError, match="频控阈值不能为负"):
        ClockLimits(siteId=1, windows={"burst": -1})


def test_missing_window_falls_back_to_default() -> None:
    from fangyu_shared.clock import DEFAULT_LIMITS

    limits = ClockLimits(siteId=1, windows={"burst": 5})
    assert limits.limit_for(WINDOW_BURST) == 5
    assert limits.limit_for(WINDOW_SHORT) == DEFAULT_LIMITS["short"]

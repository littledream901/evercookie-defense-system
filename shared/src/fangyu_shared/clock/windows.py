"""Clock 窗口定义与键构造。

为什么放在 shared
-----------------
旧版把窗口常量在 gateway 的 ``bucket.py`` 和 admin-api 的 ``clock_status.py``
里各硬编码了一份，改一边不同步，监控面板显示的窗口与实际统计口径长期不一致。
本模块是窗口语义的唯一来源，两侧都从这里导入。

单 ZSet 承载多级窗口
--------------------
旧版为 1s/60s/1h 各建一套键（还混用了 ZSet 与 Hash，导致 ``WRONGTYPE`` 静默
失败）。这里改为**一个 ZSet 存原始事件时间点**，不同窗口通过
``ZCOUNT(now-window, now)`` 从同一份数据算出，写入成本降到一次，且不存在多套
键之间的一致性问题。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_KEY_PREFIX = "fangyu:clock"


class ClockDimension(str, Enum):
    """频控维度。

    IP 与指纹是两条独立的限流轴：同一 IP 下可能有多台设备（NAT/企业出口），
    同一指纹也可能换 IP（移动网络切换）。两者都要各自计数。
    """

    IP = "ip"
    FINGERPRINT = "fp"


@dataclass(frozen=True, slots=True)
class ClockWindow:
    """一个统计窗口。

    ``name`` 用于阈值配置与超限原因文案；``seconds`` 是**真实**窗口宽度。
    旧版 ``BUCKET_60S_WINDOW = 180`` 这种名实不符的情况在此类型下无法出现，
    因为名字和秒数在同一个对象里成对声明。
    """

    name: str
    seconds: int

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(f"窗口宽度必须为正: {self.name}={self.seconds}")


WINDOW_BURST = ClockWindow("burst", 10)
"""突发窗口：10 秒。挡住脚本的密集点击。"""

WINDOW_SHORT = ClockWindow("short", 60)
"""短窗口：60 秒。常规频控主力。"""

WINDOW_HOUR = ClockWindow("hour", 3600)
"""小时窗口：3600 秒。识别长时间低频扫描。"""

ALL_WINDOWS: tuple[ClockWindow, ...] = (WINDOW_BURST, WINDOW_SHORT, WINDOW_HOUR)
"""全部窗口，按宽度升序。判定时按此顺序遍历，先命中窄窗口。"""

RETENTION_SECONDS = WINDOW_HOUR.seconds + 300
"""ZSet 保留时长：最宽窗口 + 5 分钟冗余。

冗余是为了让边界请求仍能算准最宽窗口，同时保证键最终会自然过期，
不需要旧版 ``cleanup_expired`` 那种全库 scan 的清理任务。
"""

MAX_BEHAVIOR_EVENTS_PER_REQUEST = 50
"""单请求允许携带的行为事件数上限。超出部分丢弃，防止请求体放大攻击。"""

BEHAVIOR_RETENTION_SECONDS = 1800
"""行为时序保留 30 分钟。够覆盖一次会话，又不至于无界增长。"""

BEHAVIOR_MAX_SEQUENCE = 2000
"""单个访客保留的行为事件条数上限，超出按时间淘汰最旧的。"""


def rate_key(app_id: int, dimension: ClockDimension, value: str) -> str:
    """频控计数键。

    ``value`` 由调用方保证已脱敏（IP 走哈希），这里不做哈希以免重复计算。
    """
    return f"{_KEY_PREFIX}:rate:{app_id}:{dimension.value}:{value}"


def ban_key(app_id: int, dimension: ClockDimension, value: str) -> str:
    """封禁键。存在即封禁，TTL 即剩余时长——不需要额外存过期时间戳。"""
    return f"{_KEY_PREFIX}:ban:{app_id}:{dimension.value}:{value}"


def ban_scan_pattern(app_id: int, dimension: ClockDimension | None = None) -> str:
    """``SCAN MATCH`` 用的封禁键通配模式。

    与 :func:`ban_key` 放在一起，是为了让「键长什么样」只有一处定义：模式
    与键构造不同步时，运维面板会列出空列表，而封禁其实还在生效——这种不一致
    从日志里看不出来。
    """
    if dimension is None:
        return f"{_KEY_PREFIX}:ban:{app_id}:*"
    return f"{_KEY_PREFIX}:ban:{app_id}:{dimension.value}:*"


def parse_ban_key(key: str) -> tuple[int, ClockDimension, str] | None:
    """把封禁键还原成 ``(app_id, 维度, 值)``。

    无法识别返回 ``None``——列表接口不能因为库里混进一条形状不符的键就整个
    500，那样运维连清理它的入口都没有。

    值本身可能含 ``:``，所以按前 5 段切分后取剩余全部作为值。
    """
    parts = key.split(":", 5)
    if len(parts) < 6:
        return None
    ns, sub, kind, app_raw, dim_raw, value = parts
    if f"{ns}:{sub}" != _KEY_PREFIX or kind != "ban" or not value:
        return None
    try:
        app_id = int(app_raw)
        dimension = ClockDimension(dim_raw)
    except ValueError:
        return None
    return app_id, dimension, value


def limits_key(app_id: int) -> str:
    """站点级阈值配置键。"""
    return f"{_KEY_PREFIX}:limits:{app_id}"


def behavior_key(app_id: int, fingerprint: str) -> str:
    """行为时序键。仅按指纹维度组织——行为序列天然属于设备而非 IP。"""
    return f"{_KEY_PREFIX}:behavior:{app_id}:{fingerprint}"

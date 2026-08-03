"""时间工具。

事件流与 ClickHouse 链路统一以 UTC 为基准（``utcnow_*``）；admin 后台写 MySQL
DateTime 列与对外展示用本地时区（``local_now``），见各函数说明。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow_ms() -> int:
    return int(time.time() * 1000)


def utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_epoch_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# admin 后台业务时区
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# MySQL 会话时区，与 LOCAL_TZ 对应，让 server_default=func.now() 也落本地时间
MYSQL_TIME_ZONE = "+08:00"


def local_now() -> datetime:
    """当前本地（上海）时间，naive，用于写 MySQL DateTime 列。

    MySQL DateTime 列不存时区，序列化给前端也是不带后缀的裸串，浏览器会按本地
    时区解析。写 UTC 会让展示早 8 小时，故直接存本地墙上时间。

    ClickHouse 访问日志列是 ``DateTime64(3, 'UTC')``，那条链路仍用 ``utcnow_*``。
    """
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)

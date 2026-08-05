"""时间工具。

全系统统一使用 UTC 时间，包括 ClickHouse、MySQL/PostgreSQL。
数据库存储 UTC，API 序列化输出带时区标记的 ISO 字符串，前端按用户本地时区展示。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow_ms() -> int:
    """当前 UTC 时间戳（毫秒）。"""
    return int(time.time() * 1000)


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO 字符串，带 Z 后缀。"""
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utcnow() -> datetime:
    """当前 UTC 时间，aware datetime（带时区信息）。
    
    用于写入数据库 DateTime 列。Pydantic 序列化时会自动转为 ISO 字符串并带 Z 后缀。
    """
    return datetime.now(tz=timezone.utc)


def to_epoch_ms(dt: datetime) -> int:
    """将 datetime 转为 UTC 毫秒时间戳。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# 本地时区（仅用于日志显示或特殊业务逻辑，数据库不再使用）
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# 向后兼容：移除 MYSQL_TIME_ZONE，现在 MySQL 使用 UTC
# 如需本地时间，使用 utcnow().astimezone(LOCAL_TZ)

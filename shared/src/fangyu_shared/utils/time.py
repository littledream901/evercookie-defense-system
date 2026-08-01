"""时间工具，统一以 UTC 为基准。"""

from __future__ import annotations

import time
from datetime import datetime, timezone


def utcnow_ms() -> int:
    return int(time.time() * 1000)


def utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_epoch_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

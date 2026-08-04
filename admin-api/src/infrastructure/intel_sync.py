"""情报 Redis 同步层。

六类情报以 Hash 存储（field = 主键，value = JSON），gateway 侧用 HGET 做
O(1) 查询。CIDR 类（geo_ip / ip_profile）无法直接 HGET，gateway 侧会一次性
HGETALL 后在内存里做网段匹配，故此处也只需全量写入。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fangyu_shared.intel.keys import SYNC_TIME_KEY, intel_key
from fangyu_shared.logging import get_logger
from fangyu_shared.redis_manager import RedisManager

_logger = get_logger("admin.intel_sync")

_TTL_SECONDS = 86400  # 与 threat_intel 保持一致，防孤儿 key 永存

# 各类型的 Hash field 取值字段，与 IntelRepository._UNIQUE_KEY 对应
_FIELD_KEY: dict[str, str] = {
    "asn": "asn",
    "crawler": "pattern",
    "fingerprint": "finger_id",
    "geo_ip": "cidr",
    "ip_profile": "cidr",
}

# 同步到 Redis 的值字段（剔除 id / 时间戳 / note，减小体积）
_VALUE_FIELDS: dict[str, tuple[str, ...]] = {
    "asn": ("network_type", "country", "risk_score", "operator"),
    "crawler": ("crawler_category", "crawler_name", "is_legitimate", "risk_score"),
    "fingerprint": ("finger_type", "risk_score"),
    "geo_ip": ("country", "region", "city"),
    "ip_profile": ("network_type", "is_vpn", "is_proxy", "is_tor", "risk_score"),
}


class IntelSync:
    @classmethod
    async def full_sync(cls, intel_type: str, rows: list[dict[str, Any]]) -> int:
        """全量覆盖某类型的 Redis Hash。

        先写新 key 再 RENAME 覆盖，避免同步窗口内 gateway 读到空数据。
        """
        redis = RedisManager.get_client()
        key = intel_key(intel_type)
        field_key = _FIELD_KEY[intel_type]
        value_fields = _VALUE_FIELDS[intel_type]

        mapping: dict[str, str] = {}
        for row in rows:
            field = row.get(field_key)
            if field is None:
                continue
            payload = {f: row[f] for f in value_fields if f in row}
            mapping[str(field)] = json.dumps(payload, separators=(",", ":"))

        tmp_key = f"{key}:staging"
        async with redis.pipeline(transaction=False) as pipe:
            pipe.delete(tmp_key)
            if mapping:
                pipe.hset(tmp_key, mapping=mapping)
                pipe.expire(tmp_key, _TTL_SECONDS)
            await pipe.execute()

        if mapping:
            await redis.rename(tmp_key, key)
        else:
            await redis.delete(key)

        return len(mapping)

    @classmethod
    async def sync_all(cls, rows_by_type: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for intel_type, rows in rows_by_type.items():
            counts[intel_type] = await cls.full_sync(intel_type, rows)

        redis = RedisManager.get_client()
        await redis.set(SYNC_TIME_KEY, datetime.now(UTC).isoformat(), ex=_TTL_SECONDS)

        _logger.info("intel_sync_done", **counts)
        return counts

    @classmethod
    async def last_sync_time(cls) -> str | None:
        redis = RedisManager.get_client()
        value = await redis.get(SYNC_TIME_KEY)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

"""默认处置的 Redis 写入面，供 gateway 侧按站点读取 default 阶段兜底。

键格式：``fangyu:default_disposition:{site_id}``
序列化形状与 ScoringSync 保持一致：JSON camelCase，**刻意不设 TTL**。
默认处置是安全策略，过期后无人重建会让兜底静默退回系统放行。
"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

_KEY_PREFIX = "fangyu:default_disposition"


class DefaultDispositionSync:
    """默认处置的 Redis 写入层。

    供 admin-api 在 upsert / reset 后同步。gateway 侧在 ``RuleRepository``
    加载规则集时读取同一 key，并回退到 ``site_id=0`` 全局配置。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(site_id: int) -> str:
        return f"{_KEY_PREFIX}:{site_id}"

    async def put(self, site_id: int, *, disposition: dict) -> None:
        """写入或覆盖站点默认处置。"""
        payload = orjson.dumps(disposition)
        await self._redis.set(self._key(site_id), payload)

    async def delete(self, site_id: int) -> None:
        """删除站点配置，gateway 随即回退到全局/系统默认。"""
        await self._redis.delete(self._key(site_id))

"""评分配置的 Redis 写入面，供 gateway 侧按 app 读取阈值与权重。

键格式：``fangyu:scoring:{app_id}``
序列化形状与 ClockSync 保持一致：JSON camelCase，**刻意不设 TTL**。
评分配置是安全策略，过期后无人重建会让阈值静默退回宽松默认值。
"""

from __future__ import annotations

from typing import Any

import orjson
from redis.asyncio import Redis

_KEY_PREFIX = "fangyu:scoring"


class ScoringSync:
    """评分配置的 Redis 写入层。

    供 admin-api 在 upsert / reset 后同步，以及启动时全量预热。
    gateway 侧通过 ``ScoringConfigCache`` 读取同一 key。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(app_id: int) -> str:
        return f"{_KEY_PREFIX}:{app_id}"

    async def put(
        self,
        app_id: int,
        *,
        enabled: bool,
        threshold_suspect: int,
        threshold_hostile: int,
        weights: dict[str, int],
        disposition_suspect: dict[str, Any] | None = None,
        disposition_hostile: dict[str, Any] | None = None,
    ) -> None:
        """写入或覆盖站点评分配置。"""
        payload = orjson.dumps(
            {
                "appId": app_id,
                "enabled": enabled,
                "thresholdSuspect": threshold_suspect,
                "thresholdHostile": threshold_hostile,
                "weights": weights,
                "dispositionSuspect": disposition_suspect,
                "dispositionHostile": disposition_hostile,
            }
        )
        await self._redis.set(self._key(app_id), payload)

    async def delete(self, app_id: int) -> None:
        """删除站点配置，gateway 随即回退到全局默认阈值。"""
        await self._redis.delete(self._key(app_id))

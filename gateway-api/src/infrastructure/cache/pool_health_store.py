"""地址池健康状态存储（FAILOVER 策略与健康检查用）。"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis


class PoolHealthStore:
    """地址池健康状态存储。

    Redis key 设计
    --------------
    ``fangyu:pool_health:{app_id}:{url_hash}``
    值为 "healthy" 或 "unhealthy"，TTL 300s（5 分钟未探测则过期视为健康）。

    为什么用哈希而非完整 URL
    ----------------------
    URL 可能很长（最长 1024），直接作为 key 会让 Redis 内存占用与扫描成本
    失控。blake2b(16) 碰撞概率在地址池规模（单站点数十个）下可忽略。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _url_hash(self, url: str) -> str:
        """URL 哈希，用于 key 中。"""
        return hashlib.blake2b(url.encode("utf-8"), digest_size=16).hexdigest()

    def _key(self, app_id: int, url: str) -> str:
        return f"fangyu:pool_health:{app_id}:{self._url_hash(url)}"

    async def mark_healthy(self, app_id: int, url: str, ttl: int = 300) -> None:
        """标记地址为健康（探测成功时调用）。"""
        key = self._key(app_id, url)
        await self._redis.setex(key, ttl, "healthy")

    async def mark_unhealthy(self, app_id: int, url: str, ttl: int = 300) -> None:
        """标记地址为不健康（探测失败时调用）。"""
        key = self._key(app_id, url)
        await self._redis.setex(key, ttl, "unhealthy")

    async def is_healthy(self, app_id: int, url: str) -> bool:
        """检查地址是否健康。未标记时默认健康（探测尚未覆盖的地址乐观放行）。"""
        key = self._key(app_id, url)
        val = await self._redis.get(key)
        if val is None:
            return True  # 未标记 = 探测尚未覆盖，乐观放行
        return val.decode("utf-8") == "healthy"

    async def reset(self, app_id: int, url: str) -> None:
        """重置地址健康状态（规则修改地址池时调用）。"""
        key = self._key(app_id, url)
        await self._redis.delete(key)

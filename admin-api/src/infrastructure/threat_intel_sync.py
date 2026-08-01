"""威胁情报 Redis 同步层。

Gateway 侧用 SISMEMBER 做 O(1) 查询，Admin 侧负责写入/刷新 Redis SET。
Redis Key 命名规则：fangyu:threat_intel:{category}
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.redis_manager import RedisManager

_PREFIX = "fangyu:threat_intel"
_ALL_KEY = f"{_PREFIX}:all"
_TTL_SECONDS = 86400  # 24h，防止孤儿 key 永存


class ThreatIntelSync:
    @staticmethod
    def _key(category: str) -> str:
        return f"{_PREFIX}:{category}"

    @classmethod
    async def add(cls, ip: str, category: str = "malicious") -> None:
        redis = RedisManager.get_client()
        async with redis.pipeline(transaction=False) as pipe:
            pipe.sadd(_ALL_KEY, ip)
            pipe.sadd(cls._key(category), ip)
            pipe.expire(_ALL_KEY, _TTL_SECONDS)
            pipe.expire(cls._key(category), _TTL_SECONDS)
            await pipe.execute()

    @classmethod
    async def remove(cls, ip: str, category: str = "malicious") -> None:
        redis = RedisManager.get_client()
        async with redis.pipeline(transaction=False) as pipe:
            pipe.srem(_ALL_KEY, ip)
            pipe.srem(cls._key(category), ip)
            await pipe.execute()

    @classmethod
    async def is_threat(cls, ip: str) -> bool:
        redis = RedisManager.get_client()
        return bool(await redis.sismember(_ALL_KEY, ip))

    @classmethod
    async def get_categories(cls, ip: str, categories: list[str]) -> list[str]:
        redis = RedisManager.get_client()
        matched: list[str] = []
        for cat in categories:
            if await redis.sismember(cls._key(cat), ip):
                matched.append(cat)
        return matched

    @classmethod
    async def full_sync(cls, ip_by_category: dict[str, list[str]]) -> None:
        redis = RedisManager.get_client()
        all_ips: set[str] = set()
        for category, ips in ip_by_category.items():
            all_ips.update(ips)
            key = cls._key(category)
            await redis.delete(key)
            if ips:
                await redis.sadd(key, *ips)
                await redis.expire(key, _TTL_SECONDS)

        await redis.delete(_ALL_KEY)
        if all_ips:
            await redis.sadd(_ALL_KEY, *all_ips)
            await redis.expire(_ALL_KEY, _TTL_SECONDS)

    @classmethod
    async def stats(cls) -> dict[str, Any]:
        redis = RedisManager.get_client()
        total = await redis.scard(_ALL_KEY)
        return {"total": total, "key": _ALL_KEY}

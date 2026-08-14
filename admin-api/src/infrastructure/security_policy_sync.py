"""安全策略 Redis 同步。"""

from __future__ import annotations

from redis.asyncio import Redis

from fangyu_shared.schemas.security import SecurityPolicy


class SecurityPolicySync:
    """安全策略 Redis 同步服务。
    
    负责将站点安全策略配置同步到 Gateway Redis 缓存。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, site_id: int) -> str:
        """生成站点安全策略 Redis key。"""
        return f"fangyu:security_policy:site:{site_id}"

    async def sync(self, policy: SecurityPolicy) -> None:
        """同步站点安全策略到 Redis。"""
        key = self._key(policy.site_id)
        value = policy.model_dump_json(by_alias=True)
        # 30 天 TTL，定期重建或站点更新时刷新
        await self._redis.set(key, value, ex=86400 * 30)

    async def delete(self, site_id: int) -> None:
        """删除站点安全策略缓存（重置为默认）。"""
        key = self._key(site_id)
        await self._redis.delete(key)

    async def sync_batch(self, policies: list[SecurityPolicy]) -> None:
        """批量同步多个站点的安全策略。"""
        if not policies:
            return
        async with self._redis.pipeline() as pipe:
            for policy in policies:
                key = self._key(policy.site_id)
                value = policy.model_dump_json(by_alias=True)
                pipe.set(key, value, ex=86400 * 30)
            await pipe.execute()

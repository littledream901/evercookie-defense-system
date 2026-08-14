"""安全策略缓存。"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

from fangyu_shared.schemas.security import SecurityPolicy


class SecurityPolicyCache:
    """安全策略缓存。
    
    从 Redis 加载站点安全策略配置，未配置时返回安全默认值（全部 deny）。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, site_id: int) -> str:
        """生成站点安全策略 Redis key。"""
        return f"fangyu:security_policy:site:{site_id}"

    async def get(self, site_id: int) -> SecurityPolicy:
        """获取站点安全策略配置。
        
        未配置时返回默认值：所有检查器启用 + action=deny。
        """
        key = self._key(site_id)
        raw = await self._redis.get(key)
        if raw is None:
            return self._default_policy(site_id)
        
        try:
            data = orjson.loads(raw)
            return SecurityPolicy.model_validate(data)
        except Exception:
            # JSON 解析失败，返回默认值
            return self._default_policy(site_id)

    def _default_policy(self, site_id: int) -> SecurityPolicy:
        """未配置时的安全默认值（全部启用 + deny）。"""
        return SecurityPolicy(siteId=site_id)

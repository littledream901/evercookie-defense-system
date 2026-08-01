"""双层权限缓存：请求级 + Redis。

请求级避免同一次请求内多次查询；Redis 层跨请求命中。
V1 中每次接口都跑一遍角色→权限查询，此处彻底消除 N+1。
"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

from src.domain.rbac.policy import PermissionContext

_KEY_PREFIX = "fangyu:admin:perm"


class PermissionCache:
    def __init__(self, redis: Redis, *, ttl: int = 300) -> None:
        self._redis = redis
        self._ttl = ttl
        self._local: dict[int, PermissionContext] = {}

    async def get(self, user_id: int) -> PermissionContext | None:
        if user_id in self._local:
            return self._local[user_id]
        raw = await self._redis.get(f"{_KEY_PREFIX}:{user_id}")
        if not raw:
            return None
        try:
            data = orjson.loads(raw)
            ctx = PermissionContext(
                user_id=user_id,
                role_names=frozenset(data.get("role_names", [])),
                role_permissions=frozenset(data.get("role_permissions", [])),
            )
            self._local[user_id] = ctx
            return ctx
        except (orjson.JSONDecodeError, ValueError):
            return None

    async def set(self, context: PermissionContext) -> None:
        payload = orjson.dumps({
            "role_names": list(context.role_names),
            "role_permissions": list(context.role_permissions),
        })
        await self._redis.set(f"{_KEY_PREFIX}:{context.user_id}", payload, ex=self._ttl)
        self._local[context.user_id] = context

    async def invalidate(self, user_id: int) -> None:
        await self._redis.delete(f"{_KEY_PREFIX}:{user_id}")
        self._local.pop(user_id, None)

    def reset_request_cache(self) -> None:
        self._local.clear()

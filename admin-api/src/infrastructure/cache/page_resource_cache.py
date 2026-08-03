"""页面资源 Redis 缓存。

HASH 结构: fangyu:page_resources:{app_id}
  field = resource.name
  value = JSON {"id": int, "kind": str, "content": str, "contentType": str}
"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

from src.domain.page_resource.entities import PageResource

_KEY_PREFIX = "fangyu:page_resources"


class PageResourceCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def sync_app_resources(
        self, app_id: int, resources: list[PageResource]
    ) -> None:
        """替换整个 app 的页面资源缓存（同步 publish 时调用）。"""
        key = f"{_KEY_PREFIX}:{app_id}"
        pipe = self._redis.pipeline()
        pipe.delete(key)
        if resources:
            mapping = {
                res.name: orjson.dumps(
                    {
                        "id": res.id,
                        "kind": res.kind.value,
                        "content": res.content,
                        "contentType": res.content_type,
                    }
                )
                for res in resources
            }
            if mapping:
                pipe.hset(key, mapping=mapping)  # type: ignore[arg-type]
        await pipe.execute()

    async def upsert(self, resource: PageResource) -> None:
        """单个资源 upsert（create/update 时调用）。"""
        key = f"{_KEY_PREFIX}:{resource.app_id}"
        value = orjson.dumps(
            {
                "id": resource.id,
                "kind": resource.kind.value,
                "content": resource.content,
                "contentType": resource.content_type,
            }
        )
        await self._redis.hset(key, resource.name, value)

    async def remove(self, app_id: int, name: str) -> None:
        """单个资源删除。"""
        key = f"{_KEY_PREFIX}:{app_id}"
        await self._redis.hdel(key, name)

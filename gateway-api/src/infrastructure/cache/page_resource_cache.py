"""Gateway 侧页面资源只读缓存。

只读——内容由 admin-api 写入，gateway 仅做 HGET。
Key 结构与 admin-api 侧保持一致:
  fangyu:page_resources:{app_id}  field=name  value=JSON
"""

from __future__ import annotations

from dataclasses import dataclass

import orjson
from redis.asyncio import Redis

_KEY_PREFIX = "fangyu:page_resources"


@dataclass(slots=True)
class PageResourceEntry:
    id: int | None
    kind: str
    content: str
    content_type: str


class PageResourceCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, app_id: int, name: str) -> PageResourceEntry | None:
        """按资源名查找内容，未命中或 Redis 不可达均返回 None（fail-open）。"""
        try:
            key = f"{_KEY_PREFIX}:{app_id}"
            raw = await self._redis.hget(key, name)
        except Exception:
            return None

        if not raw:
            return None

        try:
            data = orjson.loads(raw)
            return PageResourceEntry(
                id=data.get("id"),
                kind=data.get("kind", "safe"),
                content=data.get("content", ""),
                content_type=data.get("contentType", "text/html; charset=utf-8"),
            )
        except Exception:
            return None

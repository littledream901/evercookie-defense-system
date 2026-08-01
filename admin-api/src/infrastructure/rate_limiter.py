"""基于 Redis ZSET 的滑动窗口限流器。

滑动窗口算法：
- key: 限流维度标识，例如 login:{ip}:{username}
- ZADD key score={timestamp} member={uuid}：新请求入窗口
- ZREMRANGEBYSCORE key -inf {now - window_sec}：清理过期窗口
- ZCARD key：计数当前窗口内请求数
- 如果 count > limit，拒绝；否则通过

优点：精度高，能表达"N 秒内最多 M 次"；缺点：每次需要 3 个 Redis 命令。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

class RateLimiter:
    def __init__(self, redis: Any | Callable[[], Any]) -> None:
        self._redis = redis

    async def is_allowed(
        self,
        key: str,
        *,
        limit: int,
        window_sec: int,
    ) -> tuple[bool, int]:
        redis = self._redis() if callable(self._redis) else self._redis
        now = time.time()
        window_start = now - window_sec
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(uuid.uuid4()): now})
        pipe.zcard(key)
        pipe.expire(key, window_sec + 10)
        results = await pipe.execute()
        count = results[2]
        allowed = count <= limit
        retry_after = 0 if allowed else window_sec
        return allowed, retry_after

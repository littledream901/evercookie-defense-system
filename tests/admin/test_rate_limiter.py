"""RateLimiter 单元测试（基于 Redis ZSET 滑动窗口）。"""
from __future__ import annotations

import asyncio
import time

import pytest

from src.infrastructure.rate_limiter import RateLimiter


class _InMemoryRedis:
    """模拟 Redis ZSET 操作的内存实现。"""

    def __init__(self) -> None:
        self._zsets: dict[str, dict[str, float]] = {}

    def pipeline(self):
        return _InMemoryPipeline(self)

    async def zremrangebyscore(self, key: str, min_score: str | float, max_score: str | float) -> int:
        if key not in self._zsets:
            return 0
        min_val = float("-inf") if min_score == "-inf" else float(min_score)
        max_val = float("inf") if max_score == "+inf" else float(max_score)
        zset = self._zsets[key]
        to_remove = [m for m, s in zset.items() if min_val <= s <= max_val]
        for m in to_remove:
            del zset[m]
        return len(to_remove)

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        if key not in self._zsets:
            self._zsets[key] = {}
        self._zsets[key].update(mapping)
        return len(mapping)

    async def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class _InMemoryPipeline:
    def __init__(self, redis: _InMemoryRedis) -> None:
        self._redis = redis
        self._commands: list = []

    def zremrangebyscore(self, key: str, min_score: str | float, max_score: str | float):
        self._commands.append(("zremrangebyscore", key, min_score, max_score))
        return self

    def zadd(self, key: str, mapping: dict[str, float]):
        self._commands.append(("zadd", key, mapping))
        return self

    def zcard(self, key: str):
        self._commands.append(("zcard", key))
        return self

    def expire(self, key: str, seconds: int):
        self._commands.append(("expire", key, seconds))
        return self

    async def execute(self) -> list:
        results = []
        for cmd in self._commands:
            if cmd[0] == "zremrangebyscore":
                results.append(await self._redis.zremrangebyscore(cmd[1], cmd[2], cmd[3]))
            elif cmd[0] == "zadd":
                results.append(await self._redis.zadd(cmd[1], cmd[2]))
            elif cmd[0] == "zcard":
                results.append(await self._redis.zcard(cmd[1]))
            elif cmd[0] == "expire":
                results.append(await self._redis.expire(cmd[1], cmd[2]))
        return results


@pytest.mark.asyncio
async def test_rate_limiter_allows_under_limit():
    redis = _InMemoryRedis()
    limiter = RateLimiter(redis)  # type: ignore[arg-type]
    allowed, retry_after = await limiter.is_allowed("test:key", limit=5, window_sec=60)
    assert allowed is True
    assert retry_after == 0


@pytest.mark.asyncio
async def test_rate_limiter_rejects_over_limit():
    redis = _InMemoryRedis()
    limiter = RateLimiter(redis)  # type: ignore[arg-type]
    for _ in range(5):
        allowed, _ = await limiter.is_allowed("test:key", limit=5, window_sec=60)
        assert allowed is True
    allowed, retry_after = await limiter.is_allowed("test:key", limit=5, window_sec=60)
    assert allowed is False
    assert retry_after == 60


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window_expires():
    redis = _InMemoryRedis()
    limiter = RateLimiter(redis)  # type: ignore[arg-type]
    
    # 模拟时间推移：手动清理过期窗口
    for _ in range(5):
        await limiter.is_allowed("test:key", limit=5, window_sec=1)
    
    # 超限
    allowed, _ = await limiter.is_allowed("test:key", limit=5, window_sec=1)
    assert allowed is False
    
    # 等待窗口过期
    await asyncio.sleep(1.1)
    
    # 再次请求应该通过
    allowed, retry_after = await limiter.is_allowed("test:key", limit=5, window_sec=1)
    assert allowed is True
    assert retry_after == 0


@pytest.mark.asyncio
async def test_rate_limiter_different_keys_independent():
    redis = _InMemoryRedis()
    limiter = RateLimiter(redis)  # type: ignore[arg-type]
    
    for _ in range(5):
        await limiter.is_allowed("key1", limit=5, window_sec=60)
    
    # key1 超限
    allowed, _ = await limiter.is_allowed("key1", limit=5, window_sec=60)
    assert allowed is False
    
    # key2 仍然可用
    allowed, _ = await limiter.is_allowed("key2", limit=5, window_sec=60)
    assert allowed is True

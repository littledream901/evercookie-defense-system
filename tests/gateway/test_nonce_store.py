"""NonceStore 单元测试。"""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infrastructure.cache.nonce_store import NonceStore


class _FakeRedis:
    """最小 async Redis 替身，实现 SET NX EX 语义。"""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.ttls: dict[str, int | None] = {}

    async def set(
        self,
        key: str,
        value: Any,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        self.ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        self.ttls.pop(key, None)
        return 1 if self.store.pop(key, None) is not None else 0


class _BrokenRedis:
    async def set(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("redis down")

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("redis down")


def test_key_layout():
    assert NonceStore.make_key(7, "abc") == "fangyu:nonce:7:abc"


@pytest.mark.asyncio
async def test_first_claim_succeeds():
    store = NonceStore(_FakeRedis())
    assert await store.claim(1, "n1") is True


@pytest.mark.asyncio
async def test_second_claim_is_replay():
    store = NonceStore(_FakeRedis())
    await store.claim(1, "n1")
    assert await store.claim(1, "n1") is False


@pytest.mark.asyncio
async def test_nonce_is_scoped_per_app():
    """不同应用的 nonce 空间互不干扰，否则一个应用能拒绝另一个的请求。"""
    store = NonceStore(_FakeRedis())
    assert await store.claim(1, "shared") is True
    assert await store.claim(2, "shared") is True


@pytest.mark.asyncio
async def test_empty_nonce_is_rejected():
    store = NonceStore(_FakeRedis())
    assert await store.claim(1, "") is False


@pytest.mark.asyncio
async def test_ttl_defaults_to_window():
    redis = _FakeRedis()
    await NonceStore(redis, ttl=300).claim(1, "n1")
    assert redis.ttls["fangyu:nonce:1:n1"] == 300


@pytest.mark.asyncio
async def test_ttl_override():
    redis = _FakeRedis()
    await NonceStore(redis, ttl=300).claim(1, "n1", ttl=30)
    assert redis.ttls["fangyu:nonce:1:n1"] == 30


@pytest.mark.asyncio
async def test_release_allows_reclaim():
    store = NonceStore(_FakeRedis())
    await store.claim(1, "n1")
    await store.release(1, "n1")
    assert await store.claim(1, "n1") is True


@pytest.mark.asyncio
async def test_redis_failure_fails_open():
    """网关在链路最前端，Redis 抖动不应让整站不可访问。"""
    store = NonceStore(_BrokenRedis())
    assert await store.claim(1, "n1") is True


@pytest.mark.asyncio
async def test_release_swallows_redis_failure():
    await NonceStore(_BrokenRedis()).release(1, "n1")

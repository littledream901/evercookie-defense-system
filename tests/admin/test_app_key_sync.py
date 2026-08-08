"""AppKeyRedisSync + SiteService 的单元测试。"""
from __future__ import annotations

from typing import Any

import orjson
import pytest

from src.application.services.site_service import SiteService
from src.infrastructure.cache.app_key_sync import AppKeyRedisSync


def _parse(raw: str) -> dict:
    return orjson.loads(raw)


class _FakeRedis:
    """异步 Redis 替身：只实现 ``set`` / ``get`` / ``delete``。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[tuple[str, Any]] = []

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        self.calls.append(("set", (key, value, ex)))
        return True

    async def get(self, key: str) -> str | None:
        self.calls.append(("get", key))
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        self.calls.append(("delete", key))
        return int(self.store.pop(key, None) is not None)


class _StubSite:
    """SiteModel 替身，只带 SiteService 用到的字段。"""

    def __init__(self, **kwargs: Any) -> None:
        self.id: int | None = kwargs.get("id")
        self.site_key: str = kwargs.get("site_key", "")
        self.app_id: int = kwargs.get("app_id", 1)
        self.name: str = kwargs.get("name", "")
        self.domain: str = kwargs.get("domain", "")
        self.site_secret: str = kwargs.get("site_secret", "")
        self.is_active: bool = kwargs.get("is_active", True)


class _StubSiteRepo:
    """SiteRepository 替身。"""

    def __init__(self) -> None:
        self._store: dict[int, _StubSite] = {}
        self._next_id = 1

    async def create(self, **kwargs: Any) -> _StubSite:
        site_id = self._next_id
        self._next_id += 1
        created = _StubSite(
            id=site_id,
            site_key=f"site_test{site_id:04d}",
            app_id=kwargs.get("app_id", 1),
            name=kwargs.get("name", ""),
            domain=kwargs.get("domain", ""),
            site_secret=kwargs.get("site_secret", ""),
        )
        self._store[site_id] = created
        return created

    async def get(self, site_id: int) -> _StubSite | None:
        return self._store.get(site_id)

    async def update(self, site_id: int, **kwargs: Any) -> _StubSite | None:
        existing = self._store.get(site_id)
        if existing is None:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(existing, key):
                setattr(existing, key, value)
        return existing

    async def rotate_secret(self, site_id: int, site_secret: str) -> _StubSite | None:
        """site_key 不变，只更新 site_secret。"""
        existing = self._store.get(site_id)
        if existing is None:
            return None
        existing.site_secret = site_secret
        return existing

    async def delete(self, site_id: int) -> bool:
        return self._store.pop(site_id, None) is not None


# ---------------- AppKeyRedisSync ----------------


@pytest.mark.asyncio
async def test_sync_bind_writes_mapping():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("fangyu_test", 42, "sec")
    payload = _parse(redis.store["fangyu:app_keys:fangyu_test"])
    assert payload["app_id"] == 42
    assert payload["app_secret"] == "sec"


@pytest.mark.asyncio
async def test_sync_bind_without_secret_omits_field():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k", 5)
    payload = _parse(redis.store["fangyu:app_keys:k"])
    assert payload["app_id"] == 5
    assert "app_secret" not in payload


@pytest.mark.asyncio
async def test_sync_bind_skips_when_invalid():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("", 42)
    await sync.bind("has_key", 0)
    assert redis.store == {}


@pytest.mark.asyncio
async def test_sync_bind_with_ttl():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis, ttl_seconds=90)
    await sync.bind("k", 7, "mysec")
    # bind 会写两个 key（正向映射 + 反向 secret 索引），这里只断言正向那条，
    # 不能用 calls[-1]——那是反向索引的写入。
    forward = [c for c in redis.calls if c[0] == "set" and c[1][0] == "fangyu:app_keys:k"]
    assert len(forward) == 1
    _op, (key, value, ex) = forward[0]
    assert _parse(value)["app_id"] == 7
    assert ex == 90


@pytest.mark.asyncio
async def test_sync_bind_writes_secret_reverse_index():
    """反向索引供 challenge token 按 app_id 取 secret，缺了挑战链路会静默失效。"""
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k", 7, "mysec")
    assert redis.store["fangyu:app_secrets:7"] == "mysec"


@pytest.mark.asyncio
async def test_sync_bind_without_secret_skips_reverse_index():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k", 7)
    assert "fangyu:app_secrets:7" not in redis.store


@pytest.mark.asyncio
async def test_sync_unbind_without_app_id_keeps_secret_index():
    """轮换 API Key 时 secret 未变，不能顺手清掉反向索引。"""
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k", 7, "mysec")
    await sync.unbind("k")
    assert redis.store["fangyu:app_secrets:7"] == "mysec"


@pytest.mark.asyncio
async def test_sync_unbind_with_app_id_clears_secret_index():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k", 7, "mysec")
    await sync.unbind("k", 7)
    assert redis.store == {}


@pytest.mark.asyncio
async def test_sync_unbind_removes_mapping():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k1", 1, "s")
    await sync.unbind("k1")
    assert "fangyu:app_keys:k1" not in redis.store


@pytest.mark.asyncio
async def test_sync_rebind_swaps_key():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("old", 3, "s")
    await sync.rebind("old", "new", 3, "s2")
    assert "fangyu:app_keys:old" not in redis.store
    assert _parse(redis.store["fangyu:app_keys:new"])["app_id"] == 3


@pytest.mark.asyncio
async def test_sync_rebind_same_key_only_writes():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.rebind(None, "same", 9, "s")
    assert _parse(redis.store["fangyu:app_keys:same"])["app_id"] == 9


@pytest.mark.asyncio
async def test_sync_swallows_redis_errors():
    class _Boom:
        async def set(self, *_a: Any, **_k: Any) -> None:
            raise RuntimeError("boom")

        async def delete(self, *_a: Any, **_k: Any) -> int:
            raise RuntimeError("boom")

    sync = AppKeyRedisSync(_Boom())
    # 不应抛异常
    await sync.bind("k", 1)
    await sync.unbind("k")


# ---------------- SiteService 与 sync 联动 ----------------


@pytest.mark.asyncio
async def test_site_service_create_binds_key():
    redis = _FakeRedis()
    svc = SiteService(_StubSiteRepo(), app_key_sync=AppKeyRedisSync(redis))
    site, secret = await svc.create(app_id=1, name="demo", domain="example.com")
    payload = _parse(redis.store[f"fangyu:app_keys:{site.site_key}"])
    assert payload["app_id"] == site.id
    assert payload.get("app_secret") == secret


@pytest.mark.asyncio
async def test_site_service_rotate_keeps_site_key_updates_secret():
    """轮换只更新 secret，site_key 不变，Redis key 不移动。"""
    redis = _FakeRedis()
    svc = SiteService(_StubSiteRepo(), app_key_sync=AppKeyRedisSync(redis))
    site, old_secret = await svc.create(app_id=1, name="demo", domain="example.com")
    old_key = site.site_key
    rotated, new_secret = await svc.rotate_secret(site.id)  # type: ignore[arg-type]
    assert rotated.site_key == old_key
    assert new_secret != old_secret
    payload = _parse(redis.store[f"fangyu:app_keys:{old_key}"])
    assert payload["app_id"] == site.id
    assert payload.get("app_secret") == new_secret


@pytest.mark.asyncio
async def test_site_service_delete_unbinds_key():
    redis = _FakeRedis()
    repo = _StubSiteRepo()
    svc = SiteService(repo, app_key_sync=AppKeyRedisSync(redis))
    site, _secret = await svc.create(app_id=1, name="demo", domain="example.com")
    # 激活状态不允许删除，先直接改仓储里的状态绕过业务校验
    repo._store[site.id].is_active = False  # type: ignore[index]
    await svc.delete(site.id)  # type: ignore[arg-type]
    assert redis.store == {}







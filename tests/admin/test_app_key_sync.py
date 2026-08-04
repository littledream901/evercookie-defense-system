"""AppKeyRedisSync + AppService 的单元测试。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
import pytest

from src.application.services.app_service import AppService
from src.domain.app.entities import Application, ApplicationStatus
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


class _StubRepo:
    """AppRepository 替身（与新实体契约对齐：用 site_id 替代 api_key）。"""

    def __init__(self) -> None:
        self._store: dict[int, Application] = {}
        self._next_id = 1

    async def create(self, app: Application) -> Application:
        app_id = self._next_id
        self._next_id += 1
        created = Application(
            id=app_id,
            site_id=app.site_id or f"fangyu_test{app_id:04d}",
            name=app.name,
            domain=app.domain or "example.com",
            app_secret=app.app_secret,
            owner_user_id=app.owner_user_id,
        )
        self._store[app_id] = created
        return created

    async def get(self, app_id: int) -> Application | None:
        return self._store.get(app_id)

    async def rotate_secret(self, app_id: int, app_secret: str) -> Application | None:
        """site_id 不变，只更新 app_secret。"""
        existing = self._store.get(app_id)
        if existing is None:
            return None
        existing.app_secret = app_secret
        return existing

    # 向后兼容旧测试调用 rotate_api_key
    async def rotate_api_key(self, app_id: int, new_key: str, new_secret: str | None = None) -> Application | None:
        return await self.rotate_secret(app_id, new_secret or "")

    async def delete(self, app_id: int) -> bool:
        return self._store.pop(app_id, None) is not None


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


# ---------------- AppService 与 sync 联动 ----------------


@pytest.mark.asyncio
async def test_app_service_create_binds_key():
    redis = _FakeRedis()
    svc = AppService(_StubRepo(), app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1, domain="example.com")
    payload = _parse(redis.store[f"fangyu:app_keys:{app.site_id}"])
    assert payload["app_id"] == app.id
    assert payload.get("app_secret") == app.app_secret


@pytest.mark.asyncio
async def test_app_service_rotate_keeps_site_id_updates_secret():
    """轮换只更新 secret，site_id 不变，Redis key 不移动。"""
    redis = _FakeRedis()
    svc = AppService(_StubRepo(), app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1, domain="example.com")
    old_site_id = app.site_id
    old_secret = app.app_secret
    rotated = await svc.rotate_api_key(app.id)  # type: ignore[arg-type]
    # site_id 不变，旧 Redis key 仍存在（不再删除旧 key 后重建新 key）
    assert rotated.site_id == old_site_id
    assert rotated.app_secret != old_secret
    payload = _parse(redis.store[f"fangyu:app_keys:{old_site_id}"])
    assert payload["app_id"] == app.id


@pytest.mark.asyncio
async def test_app_service_delete_unbinds_key():
    redis = _FakeRedis()
    repo = _StubRepo()
    svc = AppService(repo, app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1, domain="example.com")
    # 直接改成非 active 才允许删除（通过 repo 直接改，绕过 service 权限校验）
    stored = repo._store[app.id]
    stored.is_active = False
    await svc.delete(app.id)  # type: ignore[arg-type]
    assert redis.store == {}







"""AppKeyRedisSync + AppService 的单元测试。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from src.application.services.app_service import AppService
from src.domain.app.entities import Application, ApplicationStatus
from src.infrastructure.cache.app_key_sync import AppKeyRedisSync


class _FakeRedis:
    """异步 Redis 替身：只实现 ``set`` / ``get`` / ``delete``。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[tuple[str, Any]] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.calls.append(("set", (key, value, ex)))

    async def get(self, key: str) -> str | None:
        self.calls.append(("get", key))
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        self.calls.append(("delete", key))
        return int(self.store.pop(key, None) is not None)


class _StubRepo:
    """AppRepository 替身。"""

    def __init__(self) -> None:
        self._store: dict[int, Application] = {}
        self._next_id = 1

    async def create(self, app: Application) -> Application:
        app_id = self._next_id
        self._next_id += 1
        created = Application(
            id=app_id,
            name=app.name,
            api_key=app.api_key,
            owner_user_id=app.owner_user_id,
            status=app.status,
            description=app.description,
            domains=list(app.domains),
            created_at=datetime(2026, 7, 31),
            updated_at=datetime(2026, 7, 31),
        )
        self._store[app_id] = created
        return created

    async def get(self, app_id: int) -> Application | None:
        return self._store.get(app_id)

    async def rotate_api_key(self, app_id: int, new_key: str) -> Application | None:
        existing = self._store.get(app_id)
        if existing is None:
            return None
        existing.api_key = new_key
        return existing

    async def update(
        self,
        app_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        domains: list[str] | None = None,
        status: ApplicationStatus | None = None,
    ) -> Application | None:
        existing = self._store.get(app_id)
        if existing is None:
            return None
        if name is not None:
            existing.name = name
        if description is not None:
            existing.description = description
        if domains is not None:
            existing.domains = list(domains)
        if status is not None:
            existing.status = status
        return existing

    async def delete(self, app_id: int) -> bool:
        return self._store.pop(app_id, None) is not None


# ---------------- AppKeyRedisSync ----------------


@pytest.mark.asyncio
async def test_sync_bind_writes_mapping():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("fangyu_test", 42)
    assert redis.store["fangyu:app_keys:fangyu_test"] == "42"


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
    await sync.bind("k", 7)
    _op, (key, value, ex) = redis.calls[-1]
    assert (key, value, ex) == ("fangyu:app_keys:k", "7", 90)


@pytest.mark.asyncio
async def test_sync_unbind_removes_mapping():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("k1", 1)
    await sync.unbind("k1")
    assert "fangyu:app_keys:k1" not in redis.store


@pytest.mark.asyncio
async def test_sync_rebind_swaps_key():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.bind("old", 3)
    await sync.rebind("old", "new", 3)
    assert "fangyu:app_keys:old" not in redis.store
    assert redis.store["fangyu:app_keys:new"] == "3"


@pytest.mark.asyncio
async def test_sync_rebind_same_key_only_writes():
    redis = _FakeRedis()
    sync = AppKeyRedisSync(redis)
    await sync.rebind(None, "same", 9)
    assert redis.store["fangyu:app_keys:same"] == "9"


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
    app = await svc.create(name="demo", owner_user_id=1)
    assert redis.store[f"fangyu:app_keys:{app.api_key}"] == str(app.id)


@pytest.mark.asyncio
async def test_app_service_rotate_swaps_binding():
    redis = _FakeRedis()
    svc = AppService(_StubRepo(), app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1)
    old_key = app.api_key
    rotated = await svc.rotate_api_key(app.id)  # type: ignore[arg-type]
    assert f"fangyu:app_keys:{old_key}" not in redis.store
    assert redis.store[f"fangyu:app_keys:{rotated.api_key}"] == str(app.id)


@pytest.mark.asyncio
async def test_app_service_delete_unbinds_key():
    redis = _FakeRedis()
    repo = _StubRepo()
    svc = AppService(repo, app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1)
    # 直接改成非 active 才允许删除
    await svc.update(
        app.id,  # type: ignore[arg-type]
        name=None,
        description=None,
        domains=None,
        status=ApplicationStatus.PAUSED,
    )
    await svc.delete(app.id)  # type: ignore[arg-type]
    assert redis.store == {}


@pytest.mark.asyncio
async def test_app_service_archive_unbinds_key():
    redis = _FakeRedis()
    svc = AppService(_StubRepo(), app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1)
    key = app.api_key
    await svc.update(
        app.id,  # type: ignore[arg-type]
        name=None,
        description=None,
        domains=None,
        status=ApplicationStatus.ARCHIVED,
    )
    assert f"fangyu:app_keys:{key}" not in redis.store


@pytest.mark.asyncio
async def test_app_service_pause_keeps_binding():
    redis = _FakeRedis()
    svc = AppService(_StubRepo(), app_key_sync=AppKeyRedisSync(redis))
    app = await svc.create(name="demo", owner_user_id=1)
    key = app.api_key
    await svc.update(
        app.id,  # type: ignore[arg-type]
        name=None,
        description=None,
        domains=None,
        status=ApplicationStatus.PAUSED,
    )
    # Paused 状态是可恢复的：Redis 里映射保留
    assert redis.store[f"fangyu:app_keys:{key}"] == str(app.id)

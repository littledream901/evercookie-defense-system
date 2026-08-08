"""Admin 侧页面资源缓存 + 服务单元测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from src.domain.page_resource.entities import PageResource, PageResourceKind
from src.infrastructure.cache.page_resource_cache import PageResourceCache


# ---------- Fake Redis ----------
class _FakeRedis:
    """最小 async Redis 替身，支持 HASH 操作。"""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, bytes]] = {}

    async def hset(self, key: str, field: str | None = None, value: Any = None, *, mapping: dict | None = None) -> int:
        bucket = self._data.setdefault(key, {})
        if mapping:
            bucket.update({k: v for k, v in mapping.items()})
            return len(mapping)
        assert field is not None
        bucket[field] = value
        return 1

    async def hdel(self, key: str, *fields: str) -> int:
        bucket = self._data.get(key, {})
        removed = sum(1 for f in fields if bucket.pop(f, None) is not None)
        return removed

    async def hget(self, key: str, field: str) -> bytes | None:
        return self._data.get(key, {}).get(field)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[Any] = []

    def delete(self, key: str) -> "_FakePipeline":
        self._ops.append(("delete", key))
        return self

    def hset(self, key: str, mapping: dict) -> "_FakePipeline":
        self._ops.append(("hset", key, mapping))
        return self

    async def execute(self) -> list:
        for op in self._ops:
            if op[0] == "delete":
                self._redis._data.pop(op[1], None)
            elif op[0] == "hset":
                bucket = self._redis._data.setdefault(op[1], {})
                bucket.update(op[2])
        return []


# ---------- helpers ----------
def _make_resource(*, site_id: int = 1, name: str = "safe_page", kind: PageResourceKind = PageResourceKind.SAFE, enabled: bool = True) -> PageResource:
    return PageResource(
        id=10,
        site_id=site_id,
        name=name,
        kind=kind,
        content="<h1>Hello</h1>",
        content_type="text/html; charset=utf-8",
        enabled=enabled,
    )


# ---------- PageResourceCache ----------
@pytest.mark.asyncio
async def test_cache_upsert_writes_hash() -> None:
    redis = _FakeRedis()
    cache = PageResourceCache(redis)
    resource = _make_resource()
    await cache.upsert(resource)
    raw = await redis.hget("fangyu:page_resources:1", "safe_page")
    assert raw is not None
    data = orjson.loads(raw)
    assert data["kind"] == "safe"
    assert data["content"] == "<h1>Hello</h1>"
    assert data["contentType"] == "text/html; charset=utf-8"


@pytest.mark.asyncio
async def test_cache_remove_deletes_field() -> None:
    redis = _FakeRedis()
    cache = PageResourceCache(redis)
    resource = _make_resource()
    await cache.upsert(resource)
    await cache.remove(1, "safe_page")
    assert await redis.hget("fangyu:page_resources:1", "safe_page") is None


@pytest.mark.asyncio
async def test_sync_replaces_entire_app_hash() -> None:
    redis = _FakeRedis()
    cache = PageResourceCache(redis)
    # Pre-populate stale key
    await redis.hset("fangyu:page_resources:1", "old_page", b"stale")

    resources = [
        _make_resource(name="page_a"),
        _make_resource(name="page_b", kind=PageResourceKind.LANDING),
    ]
    await cache.sync_app_resources(1, resources)

    assert await redis.hget("fangyu:page_resources:1", "old_page") is None
    assert await redis.hget("fangyu:page_resources:1", "page_a") is not None
    assert await redis.hget("fangyu:page_resources:1", "page_b") is not None


@pytest.mark.asyncio
async def test_sync_empty_clears_key() -> None:
    redis = _FakeRedis()
    cache = PageResourceCache(redis)
    await redis.hset("fangyu:page_resources:2", "leftover", b"x")
    await cache.sync_app_resources(2, [])
    assert redis._data.get("fangyu:page_resources:2") is None


# ---------- PageResourceService (pure logic, no DB) ----------
@pytest.mark.asyncio
async def test_service_create_checks_name_conflict() -> None:
    from fangyu_shared.exceptions import BusinessRuleException
    from src.application.services.page_resource_service import PageResourceService

    repo = MagicMock()
    repo.get_by_name = AsyncMock(return_value=_make_resource())  # existing!
    repo.create = AsyncMock()
    cache = MagicMock()
    cache.upsert = AsyncMock()

    svc = PageResourceService(resource_repo=repo, resource_cache=cache)
    with pytest.raises(BusinessRuleException, match="已存在"):
        await svc.create(_make_resource(name="safe_page"))

    repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_service_create_writes_cache_when_enabled() -> None:
    from src.application.services.page_resource_service import PageResourceService

    resource = _make_resource()
    repo = MagicMock()
    repo.get_by_name = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=resource)
    cache = MagicMock()
    cache.upsert = AsyncMock()

    svc = PageResourceService(resource_repo=repo, resource_cache=cache)
    result = await svc.create(resource)
    cache.upsert.assert_awaited_once_with(resource)
    assert result is resource


@pytest.mark.asyncio
async def test_service_create_skips_cache_when_disabled() -> None:
    from src.application.services.page_resource_service import PageResourceService

    resource = _make_resource(enabled=False)
    repo = MagicMock()
    repo.get_by_name = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=resource)
    cache = MagicMock()
    cache.upsert = AsyncMock()

    svc = PageResourceService(resource_repo=repo, resource_cache=cache)
    await svc.create(resource)
    cache.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_delete_removes_from_cache() -> None:
    from src.application.services.page_resource_service import PageResourceService

    resource = _make_resource()
    repo = MagicMock()
    repo.get = AsyncMock(return_value=resource)
    repo.delete = AsyncMock(return_value=True)
    cache = MagicMock()
    cache.remove = AsyncMock()

    svc = PageResourceService(resource_repo=repo, resource_cache=cache)
    await svc.delete(10)
    cache.remove.assert_awaited_once_with(1, "safe_page")


@pytest.mark.asyncio
async def test_service_delete_missing_raises() -> None:
    from fangyu_shared.exceptions import ResourceNotFoundException
    from src.application.services.page_resource_service import PageResourceService

    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    cache = MagicMock()

    svc = PageResourceService(resource_repo=repo, resource_cache=cache)
    with pytest.raises(ResourceNotFoundException):
        await svc.delete(99)

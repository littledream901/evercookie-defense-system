"""Gateway 侧页面资源缓存 + serve_alt 内容注入单元测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infrastructure.cache.page_resource_cache import PageResourceCache, PageResourceEntry


# ---------- Fake Redis ----------
class _FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, bytes]] = {}

    async def hget(self, key: str, field: str) -> bytes | None:
        return self._data.get(key, {}).get(field)

    async def hset(self, key: str, field: str, value: bytes) -> int:
        self._data.setdefault(key, {})[field] = value
        return 1


class _BrokenRedis:
    async def hget(self, *a: Any, **kw: Any) -> Any:
        raise RedisConnectionError("redis down")


# ---------- PageResourceCache ----------
@pytest.mark.asyncio
async def test_get_returns_entry_on_hit() -> None:
    redis = _FakeRedis()
    payload = orjson.dumps({"id": 5, "kind": "safe", "content": "<p>safe</p>", "contentType": "text/html"})
    redis._data["fangyu:page_resources:1"] = {"my_page": payload}

    entry = await PageResourceCache(redis).get(1, "my_page")
    assert entry is not None
    assert entry.content == "<p>safe</p>"
    assert entry.kind == "safe"
    assert entry.content_type == "text/html"


@pytest.mark.asyncio
async def test_get_returns_none_on_miss() -> None:
    redis = _FakeRedis()
    assert await PageResourceCache(redis).get(1, "nonexistent") is None


@pytest.mark.asyncio
async def test_get_fails_open_on_redis_error() -> None:
    """Redis 不可达时 fail-open：返回 None，不抛异常。"""
    assert await PageResourceCache(_BrokenRedis()).get(1, "page") is None


@pytest.mark.asyncio
async def test_get_fails_open_on_corrupt_json() -> None:
    redis = _FakeRedis()
    redis._data["fangyu:page_resources:1"] = {"bad": b"not-json!!!"}
    assert await PageResourceCache(redis).get(1, "bad") is None


# ---------- DecisionService._enrich_serve_alt ----------
@pytest.mark.asyncio
async def test_enrich_serve_alt_injects_content() -> None:
    from fangyu_shared.schemas.disposition import Mechanism, serve_alt
    from fangyu_shared.schemas.decision import DecisionResponse
    from fangyu_shared.schemas.disposition import Verdict
    from src.application.services.decision_service import DecisionService, DecisionServiceDeps

    disposition = serve_alt("my_page")

    cache = MagicMock(spec=PageResourceCache)
    cache.get = AsyncMock(
        return_value=PageResourceEntry(id=1, kind="safe", content="<h1>safe content</h1>", content_type="text/html")
    )

    deps = MagicMock(spec=DecisionServiceDeps)
    deps.page_resource_cache = cache
    svc = DecisionService(deps)

    response = DecisionResponse(
        verdict=Verdict.TRUSTED,
        mechanism=Mechanism.SERVE_ALT,
        decidedBy="rule",
        decidedStage="decision_rule",
    )

    enriched = await svc._enrich_serve_alt(response, disposition, app_id=1)
    assert enriched.page_content == "<h1>safe content</h1>"
    cache.get.assert_awaited_once_with(1, "my_page")


@pytest.mark.asyncio
async def test_enrich_non_serve_alt_untouched() -> None:
    from fangyu_shared.schemas.disposition import Mechanism, allow
    from fangyu_shared.schemas.decision import DecisionResponse
    from fangyu_shared.schemas.disposition import Verdict
    from src.application.services.decision_service import DecisionService, DecisionServiceDeps

    disposition = allow()
    deps = MagicMock(spec=DecisionServiceDeps)
    deps.page_resource_cache = MagicMock()
    svc = DecisionService(deps)

    response = DecisionResponse(
        verdict=Verdict.TRUSTED,
        mechanism=Mechanism.PASS,
        decidedBy="default",
        decidedStage="default",
    )
    enriched = await svc._enrich_serve_alt(response, disposition, app_id=1)
    assert enriched.page_content is None
    deps.page_resource_cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_no_cache_configured_returns_unchanged() -> None:
    from fangyu_shared.schemas.disposition import Mechanism, serve_alt
    from fangyu_shared.schemas.decision import DecisionResponse
    from fangyu_shared.schemas.disposition import Verdict
    from src.application.services.decision_service import DecisionService, DecisionServiceDeps

    disposition = serve_alt("page")
    deps = MagicMock(spec=DecisionServiceDeps)
    deps.page_resource_cache = None
    svc = DecisionService(deps)

    response = DecisionResponse(
        verdict=Verdict.TRUSTED,
        mechanism=Mechanism.SERVE_ALT,
        decidedBy="rule",
        decidedStage="decision_rule",
    )
    enriched = await svc._enrich_serve_alt(response, disposition, app_id=1)
    assert enriched.page_content is None


@pytest.mark.asyncio
async def test_enrich_cache_miss_returns_unchanged() -> None:
    from fangyu_shared.schemas.disposition import Mechanism, serve_alt
    from fangyu_shared.schemas.decision import DecisionResponse
    from fangyu_shared.schemas.disposition import Verdict
    from src.application.services.decision_service import DecisionService, DecisionServiceDeps

    disposition = serve_alt("missing_page")
    cache = MagicMock(spec=PageResourceCache)
    cache.get = AsyncMock(return_value=None)

    deps = MagicMock(spec=DecisionServiceDeps)
    deps.page_resource_cache = cache
    svc = DecisionService(deps)

    response = DecisionResponse(
        verdict=Verdict.TRUSTED,
        mechanism=Mechanism.SERVE_ALT,
        decidedBy="rule",
        decidedStage="decision_rule",
    )
    enriched = await svc._enrich_serve_alt(response, disposition, app_id=1)
    assert enriched.page_content is None

"""App Key 校验中间件与解析器的单元测试。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.interfaces.http.middleware.app_key import (
    AppKeyEnforcementMiddleware,
    AppKeyResolver,
    ResolvedAppKey,
    extract_api_key,
)


class _FakeRedis:
    """最小 async Redis 替身：只实现 ``get``。"""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(store or {})

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


@dataclass
class _StubSettings:
    app_key_required: bool = True
    app_key_header: str = "X-App-Key"
    app_key_redis_prefix: str = "fangyu:app_keys:"
    app_key_cache_ttl: int = 60
    app_key_cache_max_size: int = 4096


def _build_app(
    resolver: AppKeyResolver,
    settings: _StubSettings,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        AppKeyEnforcementMiddleware,
        resolver_provider=lambda: resolver,
        settings_provider=lambda: settings,
    )

    @app.post("/v2/decide")
    async def _decide(request: Request) -> dict[str, Any]:
        state = getattr(request.state, "resolved_app_key", None)
        return {"app_id": state.app_id if state else None}

    @app.post("/v2/decide/fast")
    async def _decide_fast(request: Request) -> dict[str, Any]:
        state = getattr(request.state, "resolved_app_key", None)
        return {"app_id": state.app_id if state else None}

    @app.post("/v2/rule/test")
    async def _rule_test(request: Request) -> dict[str, Any]:
        state = getattr(request.state, "resolved_app_key", None)
        return {"app_id": state.app_id if state else None}

    @app.get("/healthz")
    async def _healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


# ---------------- extract_api_key ----------------


class _HeaderRequest:
    """构造一个只关心 headers 的最小 Request 替身。"""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def test_extract_api_key_prefers_x_app_key_header():
    req = _HeaderRequest({"X-App-Key": "key-abc"})
    assert extract_api_key(req, header_name="X-App-Key") == "key-abc"  # type: ignore[arg-type]


def test_extract_api_key_bearer_fallback():
    req = _HeaderRequest({"Authorization": "Bearer bearer-key"})
    assert extract_api_key(req, header_name="X-App-Key") == "bearer-key"  # type: ignore[arg-type]


def test_extract_api_key_returns_none_when_absent():
    req = _HeaderRequest({})
    assert extract_api_key(req, header_name="X-App-Key") is None  # type: ignore[arg-type]


def test_extract_api_key_ignores_non_bearer_auth():
    req = _HeaderRequest({"Authorization": "Basic abcdef"})
    assert extract_api_key(req, header_name="X-App-Key") is None  # type: ignore[arg-type]


# ---------------- AppKeyResolver ----------------


@pytest.mark.asyncio
async def test_resolver_returns_none_for_missing_key():
    resolver = AppKeyResolver(_FakeRedis())
    assert await resolver.resolve("no-such") is None


@pytest.mark.asyncio
async def test_resolver_maps_valid_key():
    redis = _FakeRedis({"fangyu:app_keys:live": "42"})
    resolver = AppKeyResolver(redis)
    assert await resolver.resolve("live") == 42


@pytest.mark.asyncio
async def test_resolver_rejects_invalid_value():
    redis = _FakeRedis({"fangyu:app_keys:bad": "not-a-number"})
    resolver = AppKeyResolver(redis)
    assert await resolver.resolve("bad") is None


@pytest.mark.asyncio
async def test_resolver_rejects_non_positive_app_id():
    redis = _FakeRedis({"fangyu:app_keys:zero": "0"})
    resolver = AppKeyResolver(redis)
    assert await resolver.resolve("zero") is None


@pytest.mark.asyncio
async def test_resolver_hits_local_cache_after_first_lookup():
    redis = _FakeRedis({"fangyu:app_keys:hot": "7"})
    resolver = AppKeyResolver(redis, cache_ttl=60)
    assert await resolver.resolve("hot") == 7
    # 后端删掉数据，缓存内仍应命中
    redis.store.clear()
    assert await resolver.resolve("hot") == 7
    resolver.invalidate("hot")
    assert await resolver.resolve("hot") is None


# ---------------- AppKeyEnforcementMiddleware ----------------


@pytest.mark.asyncio
async def test_middleware_blocks_missing_key():
    resolver = AppKeyResolver(_FakeRedis())
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", json={})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_UNAUTHENTICATED"
    assert "API Key" in body["message"]


@pytest.mark.asyncio
async def test_middleware_blocks_invalid_key():
    resolver = AppKeyResolver(_FakeRedis())
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            headers={"X-App-Key": "invalid"},
            json={},
        )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_middleware_accepts_valid_key_and_injects_state():
    resolver = AppKeyResolver(_FakeRedis({"fangyu:app_keys:live": "99"}))
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            headers={"X-App-Key": "live"},
            json={},
        )
    assert resp.status_code == 200
    assert resp.json() == {"app_id": 99}


@pytest.mark.asyncio
async def test_middleware_skips_non_protected_routes():
    resolver = AppKeyResolver(_FakeRedis())
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_middleware_supports_bearer_scheme():
    resolver = AppKeyResolver(_FakeRedis({"fangyu:app_keys:bearer-live": "5"}))
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide/fast",
            headers={"Authorization": "Bearer bearer-live"},
            json={},
        )
    assert resp.status_code == 200
    assert resp.json() == {"app_id": 5}


@pytest.mark.asyncio
async def test_middleware_bypass_when_not_required():
    resolver = AppKeyResolver(_FakeRedis())
    app = _build_app(resolver, _StubSettings(app_key_required=False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", json={})
    assert resp.status_code == 200
    assert resp.json() == {"app_id": 0}


@pytest.mark.asyncio
async def test_middleware_returns_json_error_when_resolver_raises():
    class _BoomResolver:
        async def resolve(self, api_key: str) -> int | None:
            raise RuntimeError("redis down")

    app = _build_app(_BoomResolver(), _StubSettings())  # type: ignore[arg-type]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            headers={"X-App-Key": "any"},
            json={},
        )
    assert resp.status_code == 401
    assert resp.json()["code"] == "APP_KEY_RESOLVE_ERROR"


def test_resolved_app_key_dataclass_shape():
    resolved = ResolvedAppKey(app_id=1, api_key="k")
    assert resolved.app_id == 1
    assert resolved.api_key == "k"


# ---------------- /v2/rule/test 保护 ----------------
# 该接口回显规则命中逻辑，未鉴权等于允许外部枚举规则边界。


@pytest.mark.asyncio
async def test_rule_test_blocks_missing_key():
    resolver = AppKeyResolver(_FakeRedis())
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/rule/test", json={})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_rule_test_blocks_invalid_key():
    resolver = AppKeyResolver(_FakeRedis())
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/rule/test",
            headers={"X-App-Key": "invalid"},
            json={},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rule_test_accepts_valid_key():
    resolver = AppKeyResolver(_FakeRedis({"fangyu:app_keys:live": "77"}))
    app = _build_app(resolver, _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/rule/test",
            headers={"X-App-Key": "live"},
            json={},
        )
    assert resp.status_code == 200
    assert resp.json() == {"app_id": 77}

"""App Key 校验中间件与解析器的单元测试。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest
from fangyu_shared.utils.crypto import generate_nonce, sign_params
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.interfaces.http.middleware.app_key import (
    AppCredential,
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
    signature_required: bool = False
    signature_window: int = 300


class _MemoryNonceStore:
    """内存版 nonce 存储：语义与 Redis SET NX 一致。"""

    def __init__(self) -> None:
        self.seen: set[tuple[int, str]] = set()

    async def claim(self, app_id: int, nonce: str) -> bool:
        entry = (app_id, nonce)
        if entry in self.seen:
            return False
        self.seen.add(entry)
        return True


def _build_app(
    resolver: AppKeyResolver,
    settings: _StubSettings,
    nonce_store: Any | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        AppKeyEnforcementMiddleware,
        resolver_provider=lambda: resolver,
        settings_provider=lambda: settings,
        nonce_store_provider=(lambda: nonce_store) if nonce_store is not None else None,
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
        async def resolve_credential(self, api_key: str) -> AppCredential | None:
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
    assert resolved.signature_verified is False


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


# ---------------- 凭据解析（JSON / 旧格式） ----------------


@pytest.mark.asyncio
async def test_resolver_parses_json_credential():
    redis = _FakeRedis({"fangyu:app_keys:k": '{"app_id": 12, "app_secret": "sec"}'})
    cred = await AppKeyResolver(redis).resolve_credential("k")
    assert cred == AppCredential(app_id=12, app_secret="sec")


@pytest.mark.asyncio
async def test_resolver_parses_legacy_plain_int():
    """旧部署里存的是裸 app_id，升级期间必须继续可用（只是无法验签）。"""
    redis = _FakeRedis({"fangyu:app_keys:k": "9"})
    cred = await AppKeyResolver(redis).resolve_credential("k")
    assert cred == AppCredential(app_id=9, app_secret=None)


@pytest.mark.asyncio
async def test_resolver_rejects_malformed_json():
    redis = _FakeRedis({"fangyu:app_keys:k": "{not json"})
    assert await AppKeyResolver(redis).resolve_credential("k") is None


@pytest.mark.asyncio
async def test_resolver_rejects_json_without_app_id():
    redis = _FakeRedis({"fangyu:app_keys:k": '{"app_secret": "sec"}'})
    assert await AppKeyResolver(redis).resolve_credential("k") is None


@pytest.mark.asyncio
async def test_resolver_treats_empty_secret_as_absent():
    redis = _FakeRedis({"fangyu:app_keys:k": '{"app_id": 3, "app_secret": ""}'})
    cred = await AppKeyResolver(redis).resolve_credential("k")
    assert cred is not None and cred.app_secret is None


@pytest.mark.asyncio
async def test_resolver_accepts_bytes_value():
    """真实 redis-py 在未开 decode_responses 时返回 bytes。"""
    redis = _FakeRedis()
    redis.store["fangyu:app_keys:k"] = b'{"app_id": 4, "app_secret": "s"}'  # type: ignore[assignment]
    cred = await AppKeyResolver(redis).resolve_credential("k")
    assert cred == AppCredential(app_id=4, app_secret="s")


# ---------------- 签名强制 ----------------


_SIGN_REDIS = {"fangyu:app_keys:live": '{"app_id": 8, "app_secret": "top-secret"}'}


def _signed_body(secret: str = "top-secret", **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "fingerprint": "fp-123",
        "ip": "203.0.113.7",
        "timestamp": int(time.time()),
        "nonce": generate_nonce(),
    }
    params.update(overrides)
    params["sign"] = sign_params(params, secret)
    return params


def _sign_app(nonce_store: Any | None = None) -> FastAPI:
    return _build_app(
        AppKeyResolver(_FakeRedis(_SIGN_REDIS)),
        _StubSettings(signature_required=True),
        nonce_store=nonce_store,
    )


@pytest.mark.asyncio
async def test_signed_request_passes():
    app = _sign_app(_MemoryNonceStore())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=_signed_body())
    assert resp.status_code == 200
    assert resp.json() == {"app_id": 8}


@pytest.mark.asyncio
async def test_unsigned_request_is_rejected_when_required():
    app = _sign_app(_MemoryNonceStore())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json={"ip": "1.1.1.1"})
    assert resp.status_code == 401
    # 文案与「Key 无效」一致，不泄露失败原因。
    assert resp.json()["message"] == "API Key 无效或已失效"


@pytest.mark.asyncio
async def test_tampered_body_is_rejected():
    """核心目的：拿到 Key 也不能伪造画像。"""
    body = _signed_body(ip="203.0.113.7")
    body["ip"] = "8.8.8.8"
    app = _sign_app(_MemoryNonceStore())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=body)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_secret_is_rejected():
    app = _sign_app(_MemoryNonceStore())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            headers={"X-App-Key": "live"},
            json=_signed_body(secret="guessed"),
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stale_timestamp_is_rejected():
    app = _sign_app(_MemoryNonceStore())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            headers={"X-App-Key": "live"},
            json=_signed_body(timestamp=int(time.time()) - 3600),
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_replayed_nonce_is_rejected():
    app = _sign_app(_MemoryNonceStore())
    body = _signed_body()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=body)
        second = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=body)
    assert first.status_code == 200
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_failed_signature_does_not_burn_nonce():
    """验签在 nonce 之前：伪造请求不能提前烧掉合法访客的 nonce。"""
    store = _MemoryNonceStore()
    app = _sign_app(store)
    body = _signed_body()
    forged = {**body, "sign": "0" * 64}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (
            await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=forged)
        ).status_code == 401
        # 同一 nonce 的合法请求仍应通过
        assert (
            await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=body)
        ).status_code == 200


@pytest.mark.asyncio
async def test_missing_nonce_is_rejected_when_store_present():
    app = _sign_app(_MemoryNonceStore())
    body = {"ip": "203.0.113.7", "timestamp": int(time.time())}
    body["sign"] = sign_params(body, "top-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=body)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_legacy_credential_without_secret_fails_closed():
    """无密钥的旧凭据在开启验签后必须被拒，而不是静默放行。"""
    app = _build_app(
        AppKeyResolver(_FakeRedis({"fangyu:app_keys:old": "5"})),
        _StubSettings(signature_required=True),
        nonce_store=_MemoryNonceStore(),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "old"}, json=_signed_body())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_signature_not_enforced_when_disabled():
    """默认关闭时，未带 sign 的存量适配器不受影响。"""
    app = _build_app(AppKeyResolver(_FakeRedis(_SIGN_REDIS)), _StubSettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json={"ip": "1.1.1.1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_body_still_readable_by_route_after_middleware_reads_it():
    """中间件读过 body 后，下游路由必须还能拿到完整 body。"""
    app = _sign_app(_MemoryNonceStore())

    @app.post("/v2/decide/echo")
    async def _echo(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return {"fingerprint": payload.get("fingerprint")}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide/echo",
            headers={"X-App-Key": "live"},
            json=_signed_body(fingerprint="fp-echo"),
        )
    assert resp.status_code == 200
    assert resp.json() == {"fingerprint": "fp-echo"}


@pytest.mark.asyncio
async def test_signature_works_without_nonce_store():
    """未配置 nonce 存储时只做时间戳 + HMAC，不应报错。"""
    app = _sign_app(None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", headers={"X-App-Key": "live"}, json=_signed_body())
    assert resp.status_code == 200

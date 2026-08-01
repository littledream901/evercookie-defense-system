"""DecisionRateLimitMiddleware 单元测试。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.interfaces.http.middleware.app_key import ResolvedAppKey
from src.interfaces.http.middleware.decision_rate_limit import DecisionRateLimitMiddleware


class _StubRedis:
    def __init__(self) -> None:
        self.should_allow = True
        self.calls: list[str] = []

    def pipeline(self):
        return _StubPipeline(self)


class _StubPipeline:
    def __init__(self, redis: _StubRedis) -> None:
        self._redis = redis

    def zremrangebyscore(self, key: str, min_score, max_score):
        self._redis.calls.append(key)
        return self

    def zadd(self, key: str, mapping):
        return self

    def zcard(self, key: str):
        return self

    def expire(self, key: str, seconds: int):
        return self

    async def execute(self):
        count = 100 if self._redis.should_allow else 101
        return [0, 1, count, True]


def _build_app(redis) -> FastAPI:
    app = FastAPI()
    app.add_middleware(DecisionRateLimitMiddleware, redis=redis)

    @app.middleware("http")
    async def inject_app_key(request, call_next):
        resolved_id = request.headers.get("x-test-resolved-app-id")
        if resolved_id:
            request.state.resolved_app_key = ResolvedAppKey(
                app_id=int(resolved_id), api_key="resolved_key"
            )
        if request.headers.get("x-test-app-key"):
            request.state.app_key = request.headers["x-test-app-key"]
        return await call_next(request)

    @app.post("/v2/decide")
    async def decide():
        return {"action": "allow"}

    @app.post("/v2/decide/fast")
    async def decide_fast():
        return {"action": "allow"}

    @app.get("/v2/health")
    async def health():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_decision_rate_limit_allows_under_limit():
    redis = _StubRedis()
    redis.should_allow = True
    app = _build_app(redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            json={"event": "login"},
            headers={"x-test-app-key": "test_key_123"},
        )
    
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_decision_rate_limit_rejects_over_limit():
    redis = _StubRedis()
    redis.should_allow = False
    app = _build_app(redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            json={"event": "login"},
            headers={"x-test-app-key": "test_key_123"},
        )
    
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.json()["error"] == "决策频率超限，请稍后重试"


@pytest.mark.asyncio
async def test_decision_rate_limit_skips_non_decide():
    redis = _StubRedis()
    app = _build_app(redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v2/health")
    
    assert resp.status_code == 200
    assert len(redis.calls) == 0


@pytest.mark.asyncio
async def test_decision_rate_limit_falls_back_to_ip_without_app_key():
    """无 app_key 时不能静默放行，退化成按客户端 IP 限流。"""
    redis = _StubRedis()
    app = _build_app(redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/decide", json={"event": "login"})

    assert resp.status_code == 200
    assert redis.calls == ["decide:ip:127.0.0.1"]


@pytest.mark.asyncio
async def test_decision_rate_limit_prefers_resolved_app_id():
    """限流主体优先取 AppKeyEnforcementMiddleware 解析出的 app_id。"""
    redis = _StubRedis()
    app = _build_app(redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            json={"event": "login"},
            headers={"x-test-resolved-app-id": "42"},
        )

    assert resp.status_code == 200
    assert redis.calls == ["decide:app:42"]


@pytest.mark.asyncio
async def test_decision_rate_limit_covers_fast_path():
    """/v2/decide/fast 也必须纳入限流。"""
    redis = _StubRedis()
    app = _build_app(redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide/fast",
            json={"event": "login"},
            headers={"x-test-app-key": "test_key_123"},
        )

    assert resp.status_code == 200
    assert redis.calls == ["decide:key:test_key_123"]

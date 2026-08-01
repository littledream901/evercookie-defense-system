"""LoginRateLimitMiddleware 单元测试。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.rate_limiter import RateLimiter
from src.interfaces.http.middleware.login_rate_limit import LoginRateLimitMiddleware


class _StubLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self.should_allow = True

    async def is_allowed(self, key: str, *, limit: int, window_sec: int) -> tuple[bool, int]:
        self.calls.append((key, limit, window_sec))
        return (self.should_allow, 0 if self.should_allow else window_sec)


def _build_app(limiter: RateLimiter) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LoginRateLimitMiddleware, limiter=limiter)

    @app.post("/v2/auth/login")
    async def login():
        return {"ok": True}

    @app.get("/v2/users")
    async def users():
        return {"data": []}

    return app


@pytest.mark.asyncio
async def test_login_rate_limit_allows_under_limit():
    limiter = _StubLimiter()
    limiter.should_allow = True
    app = _build_app(limiter)  # type: ignore[arg-type]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/auth/login", json={"username": "admin", "password": "pass"})
    
    assert resp.status_code == 200
    assert len(limiter.calls) == 1
    key, limit, window = limiter.calls[0]
    assert "login:" in key
    assert "admin" in key
    assert limit == 5
    assert window == 60


@pytest.mark.asyncio
async def test_login_rate_limit_rejects_over_limit():
    limiter = _StubLimiter()
    limiter.should_allow = False
    app = _build_app(limiter)  # type: ignore[arg-type]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/auth/login", json={"username": "admin", "password": "pass"})
    
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.json()["error"] == "登录频率超限，请稍后重试"


@pytest.mark.asyncio
async def test_login_rate_limit_skips_non_login():
    limiter = _StubLimiter()
    app = _build_app(limiter)  # type: ignore[arg-type]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v2/users")
    
    assert resp.status_code == 200
    assert len(limiter.calls) == 0


@pytest.mark.asyncio
async def test_login_rate_limit_extracts_ip_from_xff():
    limiter = _StubLimiter()
    limiter.should_allow = True
    app = _build_app(limiter)  # type: ignore[arg-type]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/auth/login",
            json={"username": "admin", "password": "pass"},
            headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"},
        )
    
    assert resp.status_code == 200
    key = limiter.calls[0][0]
    assert "1.2.3.4" in key

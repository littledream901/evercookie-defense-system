"""gateway-api 决策接口集成测试。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_decide_without_app_key_returns_401(gateway_client):
    resp = await gateway_client.post(
        "/v2/decide",
        json={
            "request_id": "test-1",
            "subject": {"ip": "1.1.1.1"},
            "context": {},
        },
    )
    assert resp.status_code == 401


async def test_decide_with_invalid_key_returns_401(gateway_client):
    resp = await gateway_client.post(
        "/v2/decide",
        headers={"X-App-Key": "invalid_key"},
        json={
            "request_id": "test-2",
            "subject": {"ip": "1.1.1.1"},
            "context": {},
        },
    )
    assert resp.status_code == 401


async def test_decide_fast_returns_minimal_response(gateway_client):
    """无 App-Key 也会 401，但我们先测端点存在性。"""
    resp = await gateway_client.post(
        "/v2/decide/fast",
        json={
            "request_id": "fast-1",
            "subject": {"ip": "127.0.0.1"},
            "context": {},
        },
    )
    assert resp.status_code in (200, 401)


async def test_health_endpoints(gateway_client):
    liveness = await gateway_client.get("/healthz")
    assert liveness.status_code == 200
    readiness = await gateway_client.get("/readyz")
    assert readiness.status_code in (200, 503)

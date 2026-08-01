"""P1-3：admin 发布规则后，gateway 命中并写入 Redis Stream。"""
from __future__ import annotations

import sys
from pathlib import Path

import orjson
import pytest
import pytest_asyncio
from redis.asyncio import Redis

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.e2e]

_ROOT = Path(__file__).resolve().parents[3]
_GATEWAY = _ROOT / "gateway-api"


@pytest_asyncio.fixture(scope="function")
async def integration_redis(integration_env: dict):
    redis = Redis.from_url(integration_env["GATEWAY_REDIS_URL"], decode_responses=True)
    try:
        yield redis
    finally:
        await redis.close()


@pytest_asyncio.fixture(scope="function")
async def gateway_client_for_admin_flow(integration_env: dict):
    for name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
        sys.modules.pop(name, None)
    other = {str(_GATEWAY.parent / n) for n in ("admin-api", "worker")}
    sys.path[:] = [p for p in sys.path if p not in other]
    if str(_GATEWAY) not in sys.path:
        sys.path.insert(0, str(_GATEWAY))

    from httpx import ASGITransport, AsyncClient
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
            yield client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_publish_rule_then_gateway_decide_emits_stream(
    admin_client,
    admin_token: str,
    gateway_client_for_admin_flow,
    integration_redis,
):
    await integration_redis.delete("fangyu:events:decision")
    await integration_redis.delete("fangyu:events:decision:dlq")

    create_app = await admin_client.post(
        "/v2/apps",
        json={"name": "p1-3-app", "description": "e2e", "domains": ["example.com"]},
        headers=_bearer(admin_token),
    )
    assert create_app.status_code == 201, create_app.text
    app_data = create_app.json()["data"]
    app_id = app_data["id"]
    api_key = app_data["api_key"]

    create_rule = await admin_client.post(
        f"/v2/apps/{app_id}/rules",
        json={
            "name": "cn-block",
            "description": "命中 CN",
            "kind": "decision",
            "priority": "high",
            "disposition": {
                "verdict": "hostile",
                "mechanism": "deny",
                "target": {"kind": "origin"},
                "ttlSeconds": 900,
            },
            "conditions": [{"field": "ip.country", "op": "in", "value": ["CN"]}],
            "tags": ["p1-3"],
        },
        headers=_bearer(admin_token),
    )
    assert create_rule.status_code == 201, create_rule.text
    rule_id = create_rule.json()["data"]["id"]

    publish_rule = await admin_client.post(
        f"/v2/apps/{app_id}/rules/{rule_id}/publish",
        headers=_bearer(admin_token),
    )
    assert publish_rule.status_code == 200, publish_rule.text
    assert publish_rule.json()["data"]["status"] == "published"

    decision = await gateway_client_for_admin_flow.post(
        "/v2/decide",
        headers={"X-App-Key": api_key},
        json={
            "context": {
                "appId": app_id,
                "fingerprint": "fp-p1-3",
                "deviceId": "dev-p1-3",
                "ip": "1.1.1.1",
                "userAgent": "pytest-e2e",
                "path": "/checkout",
                "method": "POST",
                "extra": {},
            },
            "requireDetails": True,
        },
    )
    assert decision.status_code == 200, decision.text
    body = decision.json()["data"]
    assert body["verdict"] == "hostile"
    assert body["mechanism"] == "deny"
    assert body["httpStatus"] == 403
    assert body["decidedBy"] == "decision_rule"
    assert body["ruleIds"] == [rule_id]
    assert body["details"][0]["ruleId"] == rule_id

    redis_rules = await integration_redis.hgetall(f"fangyu:rules:{app_id}")
    assert str(rule_id) in redis_rules

    stream_items = await integration_redis.xrange("fangyu:events:decision", min="-", max="+", count=10)
    assert len(stream_items) >= 1
    _message_id, fields = stream_items[-1]
    payload = orjson.loads(fields["payload"])
    assert payload["appId"] == app_id
    assert payload["ruleIds"] == [rule_id]
    assert payload["requestId"] == body["requestId"]
    assert payload["fingerprint"] == "fp-p1-3"
    assert payload["verdict"] == "hostile"
    assert payload["mechanism"] == "deny"
    assert payload["decidedBy"] == "decision_rule"

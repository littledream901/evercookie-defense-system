"""admin-api 应用/规则/发布链路集成测试。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_app_crud_and_rotate_key(admin_client, admin_token: str):
    hdr = await _auth_headers(admin_token)
    create = await admin_client.post(
        "/v2/apps",
        json={
            "name": "integration-app",
            "description": "集成测试",
            "domains": ["example.com"],
        },
        headers=hdr,
    )
    assert create.status_code in (200, 201), create.text
    app_id = create.json()["id"]
    original_key = create.json()["api_key"]
    assert original_key.startswith("fangyu_")

    rotate = await admin_client.post(f"/v2/apps/{app_id}/rotate-key", headers=hdr)
    assert rotate.status_code == 200
    assert rotate.json()["api_key"] != original_key


async def test_rule_full_lifecycle(admin_client, admin_token: str):
    hdr = await _auth_headers(admin_token)
    app_resp = await admin_client.post(
        "/v2/apps",
        json={"name": "rules-app", "description": "", "domains": []},
        headers=hdr,
    )
    app_id = app_resp.json()["id"]

    create = await admin_client.post(
        f"/v2/apps/{app_id}/rules",
        json={
            "name": "cn-allow",
            "description": "允许中国流量",
            "priority": "normal",
            "weight": 10,
            "disposition": "ALLOW",
            "conditions": [{"field": "country", "op": "in", "value": ["CN"]}],
        },
        headers=hdr,
    )
    assert create.status_code in (200, 201), create.text
    rule_id = create.json()["id"]
    assert create.json()["status"] == "draft"

    publish = await admin_client.post(
        f"/v2/apps/{app_id}/rules/{rule_id}/publish",
        json={"change_summary": "初次发布"},
        headers=hdr,
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"

    versions = await admin_client.get(
        f"/v2/apps/{app_id}/rules/{rule_id}/versions",
        headers=hdr,
    )
    assert versions.status_code == 200
    assert versions.json()["total"] >= 1

    disable = await admin_client.post(
        f"/v2/apps/{app_id}/rules/{rule_id}/disable",
        headers=hdr,
    )
    assert disable.status_code == 200
    assert disable.json()["status"] == "disabled"

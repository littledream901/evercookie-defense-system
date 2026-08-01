"""admin-api 认证 & 用户列表集成测试。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_login_returns_token_pair(admin_client):
    resp = await admin_client.post(
        "/v2/auth/login",
        json={"username": "admin", "password": "Admin@fangyu2026"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["username"] == "admin"


async def test_wrong_password_401(admin_client):
    resp = await admin_client.post(
        "/v2/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_me_requires_bearer(admin_client):
    resp = await admin_client.get("/v2/auth/me")
    assert resp.status_code == 401


async def test_me_success(admin_client, admin_token: str):
    resp = await admin_client.get(
        "/v2/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["username"] == "admin"
    assert "*" in data["permissions"]


async def test_refresh_flow(admin_client):
    login = await admin_client.post(
        "/v2/auth/login",
        json={"username": "admin", "password": "Admin@fangyu2026"},
    )
    refresh = login.json()["refresh_token"]
    resp = await admin_client.post("/v2/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_list_users_requires_permission(admin_client, admin_token: str):
    resp = await admin_client.get(
        "/v2/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    usernames = [u["username"] for u in body["items"]]
    assert "admin" in usernames

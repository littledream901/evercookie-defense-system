"""审计日志：service / middleware 单元测试。

repository 层依赖真实 MySQL，走到集成测试；这里只用内存 stub 覆盖行为。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.application.services.audit_service import AuditService
from src.domain.audit.entities import AuditAction, AuditLog
from src.interfaces.http.middleware.audit_log import (
    AuditLogMiddleware,
    _extract_resource,
    _infer_action,
)


class _InMemoryRepo:
    def __init__(self) -> None:
        self.rows: list[AuditLog] = []

    async def create(self, log: AuditLog) -> AuditLog:
        log.id = len(self.rows) + 1
        self.rows.append(log)
        return log

    async def list_paged(self, **kw: Any) -> tuple[list[AuditLog], int]:
        rows = list(self.rows)
        if kw.get("user_id") is not None:
            rows = [r for r in rows if r.user_id == kw["user_id"]]
        if kw.get("resource"):
            rows = [r for r in rows if r.resource == kw["resource"]]
        if kw.get("action"):
            rows = [r for r in rows if r.action == kw["action"]]
        rows.sort(key=lambda r: r.occurred_at, reverse=True)
        offset = kw.get("offset", 0)
        limit = kw.get("limit", 20)
        return rows[offset : offset + limit], len(rows)


# ---------- Service ----------


@pytest.mark.asyncio
async def test_audit_service_record_creates_row():
    repo = _InMemoryRepo()
    svc = AuditService(repo)  # type: ignore[arg-type]
    log = await svc.record(
        user_id=1,
        username="admin",
        method="POST",
        path="/v2/apps",
        resource="apps",
        action=AuditAction.CREATE.value,
        status_code=200,
        ip="1.2.3.4",
    )
    assert log.id == 1
    assert repo.rows[0].method == "POST"


@pytest.mark.asyncio
async def test_audit_service_list_paged_filters():
    repo = _InMemoryRepo()
    svc = AuditService(repo)  # type: ignore[arg-type]
    for i in range(3):
        await svc.record(
            user_id=1 if i < 2 else 2,
            username="u",
            method="POST",
            path=f"/v2/apps/{i}",
            resource="apps",
            action=AuditAction.CREATE.value,
        )
    items, total = await svc.list_paged(
        user_id=1,
        resource=None,
        action=None,
        start_at=None,
        end_at=None,
        keyword=None,
        page=1,
        page_size=10,
    )
    assert total == 2
    assert len(items) == 2
    assert all(x.user_id == 1 for x in items)


# ---------- 辅助函数 ----------


def test_extract_resource_with_id():
    assert _extract_resource("/v2/apps/123") == ("apps", "123")


def test_extract_resource_without_id():
    assert _extract_resource("/v2/apps") == ("apps", "")


def test_extract_resource_treats_sub_action_not_as_id():
    # /v2/apps/rotate-key 中的 rotate-key 不是数字/uuid，视为子操作路径
    assert _extract_resource("/v2/apps/rotate-key") == ("apps", "")


def test_extract_resource_matches_uuid_like():
    assert _extract_resource("/v2/apps/abcdef1234") == ("apps", "abcdef1234")


def test_infer_action_by_method():
    assert _infer_action("POST", "/v2/apps") == AuditAction.CREATE.value
    assert _infer_action("PUT", "/v2/apps/1") == AuditAction.UPDATE.value
    assert _infer_action("PATCH", "/v2/apps/1") == AuditAction.UPDATE.value
    assert _infer_action("DELETE", "/v2/apps/1") == AuditAction.DELETE.value


def test_infer_action_by_subpath():
    assert _infer_action("POST", "/v2/auth/login") == AuditAction.LOGIN.value
    assert _infer_action("POST", "/v2/apps/1/rotate-api-key") == AuditAction.ROTATE.value
    assert _infer_action("POST", "/v2/rules/1/publish") == AuditAction.PUBLISH.value
    assert _infer_action("POST", "/v2/rules/1/disable") == AuditAction.DISABLE.value


# ---------- Middleware ----------


def _build_middleware_app(recorder):
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware, recorder=recorder)

    @app.get("/v2/apps")
    async def _list():
        return {"data": []}

    @app.post("/v2/apps")
    async def _create():
        return {"data": {"id": 1}}

    @app.put("/v2/apps/1")
    async def _update():
        return {"data": {"id": 1}}

    @app.delete("/v2/apps/1")
    async def _delete():
        return {"data": {}}

    @app.post("/v2/auth/refresh")
    async def _refresh():
        return {"ok": True}

    @app.get("/healthz")
    async def _health():
        return {"ok": True}

    return app


async def _wait_audit(client_response) -> None:
    task = client_response.request.extensions.get("audit_task")  # 不可靠：httpx 不透传
    if task:
        await task


@pytest.mark.asyncio
async def test_middleware_skips_get():
    calls: list[dict] = []

    async def recorder(payload: dict) -> None:
        calls.append(payload)

    app = _build_middleware_app(recorder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v2/apps")
    assert resp.status_code == 200
    await asyncio.sleep(0.05)
    assert calls == []


@pytest.mark.asyncio
async def test_middleware_skips_whitelist_paths():
    calls: list[dict] = []

    async def recorder(payload: dict) -> None:
        calls.append(payload)

    app = _build_middleware_app(recorder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v2/auth/refresh", json={})
    await asyncio.sleep(0.05)
    assert calls == []


@pytest.mark.asyncio
async def test_middleware_records_create():
    calls: list[dict] = []
    done = asyncio.Event()

    async def recorder(payload: dict) -> None:
        calls.append(payload)
        done.set()

    app = _build_middleware_app(recorder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v2/apps",
            json={"name": "demo"},
            headers={"user-agent": "pytest/1.0", "x-request-id": "req-123"},
        )
    assert resp.status_code == 200
    await asyncio.wait_for(done.wait(), timeout=2)
    payload = calls[0]
    assert payload["method"] == "POST"
    assert payload["path"] == "/v2/apps"
    assert payload["resource"] == "apps"
    assert payload["resource_id"] == ""
    assert payload["action"] == AuditAction.CREATE.value
    assert payload["status_code"] == 200
    assert payload["request_id"] == "req-123"
    assert payload["user_agent"] == "pytest/1.0"


@pytest.mark.asyncio
async def test_middleware_records_update_with_resource_id():
    calls: list[dict] = []
    done = asyncio.Event()

    async def recorder(payload: dict) -> None:
        calls.append(payload)
        done.set()

    app = _build_middleware_app(recorder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/v2/apps/1", json={"name": "renamed"})
    await asyncio.wait_for(done.wait(), timeout=2)
    payload = calls[0]
    assert payload["resource"] == "apps"
    assert payload["resource_id"] == "1"
    assert payload["action"] == AuditAction.UPDATE.value


@pytest.mark.asyncio
async def test_middleware_records_delete_and_captures_status():
    calls: list[dict] = []
    done = asyncio.Event()

    async def recorder(payload: dict) -> None:
        calls.append(payload)
        done.set()

    app = _build_middleware_app(recorder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.delete("/v2/apps/1")
    await asyncio.wait_for(done.wait(), timeout=2)
    payload = calls[0]
    assert payload["action"] == AuditAction.DELETE.value
    assert payload["status_code"] == 200


@pytest.mark.asyncio
async def test_middleware_swallows_recorder_error():
    async def recorder(payload: dict) -> None:
        raise RuntimeError("db down")

    app = _build_middleware_app(recorder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v2/apps", json={"name": "demo"})
    # 主响应不应被 recorder 异常污染
    assert resp.status_code == 200
    await asyncio.sleep(0.1)


def test_audit_log_entity_defaults():
    log = AuditLog()
    assert log.action == AuditAction.OTHER.value
    assert isinstance(log.occurred_at, datetime)

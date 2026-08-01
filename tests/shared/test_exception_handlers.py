"""异常处理器测试：重点覆盖校验错误的 JSON 序列化安全。

回归背景
--------
自定义校验器抛 ``ValueError`` 时，``RequestValidationError.errors()`` 会在
``ctx.error`` 里带上原始异常对象。直接塞进 JSONResponse 会在序列化阶段抛
TypeError，导致本该是 422 的响应变成 500，且真实校验原因全部丢失。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, field_validator

from fangyu_shared.exceptions.handlers import register_exception_handlers


class _Payload(BaseModel):
    name: str = Field(..., min_length=2)
    kind: str

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in {"a", "b"}:
            raise ValueError(f"不支持的种类: {v}")
        return v


@pytest.fixture
def client_app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/echo")
    async def _echo(payload: _Payload) -> dict:
        return {"ok": True, "name": payload.name}

    return app


async def _post(app, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/echo", json=body)


@pytest.mark.asyncio
async def test_valid_payload_passes(client_app):
    resp = await _post(client_app, {"name": "ok", "kind": "a"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_builtin_constraint_returns_422(client_app):
    resp = await _post(client_app, {"name": "x", "kind": "a"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALID_FAILED"


@pytest.mark.asyncio
async def test_custom_validator_error_returns_422_not_500(client_app):
    """核心回归：自定义校验器抛 ValueError 不应变成 500。"""
    resp = await _post(client_app, {"name": "ok", "kind": "zzz"})
    assert resp.status_code == 422, f"期望 422，实际 {resp.status_code}"
    body = resp.json()
    assert body["code"] == "VALID_FAILED"
    errors = body["details"]["errors"]
    assert errors, "错误详情不应为空"
    # 真实校验原因必须保留下来，而不是被序列化失败吞掉
    assert any("zzz" in str(e.get("msg", "")) for e in errors)


@pytest.mark.asyncio
async def test_error_details_are_json_serializable(client_app):
    """ctx.error 被清洗成字符串，整个响应体可被 json 解析。"""
    resp = await _post(client_app, {"name": "ok", "kind": "bad"})
    assert resp.status_code == 422
    for err in resp.json()["details"]["errors"]:
        assert isinstance(err["loc"], list)
        assert all(isinstance(x, str) for x in err["loc"])
        if "ctx" in err:
            assert all(isinstance(v, str) for v in err["ctx"].values())


@pytest.mark.asyncio
async def test_missing_field_reports_location(client_app):
    resp = await _post(client_app, {"kind": "a"})
    assert resp.status_code == 422
    locs = [e["loc"] for e in resp.json()["details"]["errors"]]
    assert any("name" in loc for loc in locs)


@pytest.mark.asyncio
async def test_multiple_errors_all_reported(client_app):
    resp = await _post(client_app, {"name": "x", "kind": "nope"})
    assert resp.status_code == 422
    assert len(resp.json()["details"]["errors"]) >= 2

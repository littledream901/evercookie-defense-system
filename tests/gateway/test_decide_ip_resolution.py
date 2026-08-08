"""``context.ip`` 的按来源解析。

覆盖两条不同的信任模型：

- ``ingress=sdk``：浏览器不知道自己的出口 IP，服务端从 socket peer 覆写。
  客户端上报值一律不作数——否则任何持有 API Key 的人都能伪造干净 IP。
- ``ingress=adapter``：站点服务端才知道访客 IP，保留其上报值；此时 socket
  peer 是站点服务器本身。
"""
from __future__ import annotations

from typing import Any

import pytest
from fangyu_shared.schemas.decision import (
    DecisionContext,
    DecisionRequest,
    IngressKind,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key
from src.interfaces.http.v2 import decide as decide_module


# ── schema 层 ──


def test_sdk_context_allows_missing_ip() -> None:
    """SDK 路径可以不带 IP：浏览器结构上无法得知。"""
    ctx = DecisionContext(
        siteId=1,
        ingress=IngressKind.SDK,
        fingerprint="fp_abc",
        userAgent="Mozilla/5.0",
    )
    assert ctx.ip is None


def test_adapter_context_requires_ip() -> None:
    """Adapter 路径必须带 IP：gateway 看到的 socket peer 是站点服务器。"""
    with pytest.raises(ValidationError, match="ingress=adapter 必须提供 ip"):
        DecisionContext(
            siteId=1,
            ingress=IngressKind.ADAPTER,
            userAgent="Mozilla/5.0",
        )


def test_adapter_derived_fingerprint_still_works_with_ip() -> None:
    ctx = DecisionContext(
        siteId=1,
        ingress=IngressKind.ADAPTER,
        ip="203.0.113.9",
        userAgent="Mozilla/5.0",
    )
    assert ctx.fingerprint.startswith("adapter:")
    assert ctx.fingerprint_is_derived is True


def test_sdk_context_still_requires_fingerprint() -> None:
    """放开 ip 不能顺带放开 fingerprint。"""
    with pytest.raises(ValidationError, match="ingress=sdk 必须提供 fingerprint"):
        DecisionContext(siteId=1, ingress=IngressKind.SDK, userAgent="Mozilla/5.0")


# ── 路由层 ──


class _CapturingService:
    """记录 decide() 收到的上下文。"""

    def __init__(self) -> None:
        self.seen: list[DecisionContext] = []

    async def decide(self, request: DecisionRequest) -> Any:
        self.seen.append(request.context)
        from fangyu_shared.schemas.decision import DecisionResponse

        return DecisionResponse(verdict="trusted", mechanism="pass", requestId="rid")


def _build(service: _CapturingService, site_id: int = 1) -> FastAPI:
    app = FastAPI()
    app.include_router(decide_module.router, prefix="/v2")
    app.dependency_overrides[require_app_key] = lambda: ResolvedAppKey(
        site_id=site_id, api_key="k"
    )
    app.dependency_overrides[decide_module.get_decision_service] = lambda: service
    return app


def _sdk_body(**ctx_overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "siteId": 1,
        "ingress": "sdk",
        "fingerprint": "fp_abc",
        "userAgent": "Mozilla/5.0",
    }
    context.update(ctx_overrides)
    return {"context": context}


@pytest.mark.asyncio
async def test_sdk_ip_filled_from_socket_peer() -> None:
    service = _CapturingService()
    transport = ASGITransport(app=_build(service), client=("198.51.100.7", 1234))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide", json=_sdk_body())

    assert resp.status_code == 200
    assert str(service.seen[0].ip) == "198.51.100.7"


@pytest.mark.asyncio
async def test_sdk_client_reported_ip_is_overridden() -> None:
    """关键安全断言：客户端自报 IP 必须被 socket peer 覆盖。"""
    service = _CapturingService()
    transport = ASGITransport(app=_build(service), client=("198.51.100.7", 1234))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide", json=_sdk_body(ip="1.1.1.1"))

    assert resp.status_code == 200
    assert str(service.seen[0].ip) == "198.51.100.7"


@pytest.mark.asyncio
async def test_x_forwarded_for_is_ignored() -> None:
    """XFF 可由客户端任意伪造，取 IP 时不得采信；X-Real-IP 由受信代理写入。"""
    service = _CapturingService()
    transport = ASGITransport(app=_build(service), client=("198.51.100.7", 1234))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            json=_sdk_body(),
            headers={"X-Forwarded-For": "9.9.9.9", "X-Real-IP": "8.8.8.8"},
        )

    assert resp.status_code == 200
    assert str(service.seen[0].ip) == "8.8.8.8"


@pytest.mark.asyncio
async def test_adapter_ip_is_preserved() -> None:
    """Adapter 上报的访客 IP 不能被 socket peer 覆盖。"""
    service = _CapturingService()
    transport = ASGITransport(app=_build(service), client=("198.51.100.7", 1234))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v2/decide",
            json={
                "context": {
                    "siteId": 1,
                    "ingress": "adapter",
                    "ip": "203.0.113.9",
                    "userAgent": "Mozilla/5.0",
                }
            },
        )

    assert resp.status_code == 200
    assert str(service.seen[0].ip) == "203.0.113.9"


@pytest.mark.asyncio
async def test_decide_fast_resolves_ip_too() -> None:
    """快通道不能漏掉 IP 解析，否则会把 None 送进服务层。"""
    service = _CapturingService()
    transport = ASGITransport(app=_build(service), client=("198.51.100.7", 1234))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide/fast", json=_sdk_body())

    assert resp.status_code == 200
    assert str(service.seen[0].ip) == "198.51.100.7"


def _request_without_peer() -> Any:
    """构造一个 ``client`` 为 None 的 Request。

    ASGITransport 总会填一个默认 client，走 HTTP 客户端测不到这条路径，
    因此直接单元测试解析函数。真实场景对应异常传输层或非 TCP 的 ASGI 服务器。
    """
    from starlette.requests import Request

    return Request({"type": "http", "method": "POST", "path": "/v2/decide", "headers": []})


def test_missing_socket_peer_and_no_reported_ip_is_rejected() -> None:
    """既无 socket peer 也无上报值时显式拒绝，不静默降级成 None。"""
    from fangyu_shared.exceptions import ValidationException

    payload = DecisionRequest.model_validate(_sdk_body())
    with pytest.raises(ValidationException, match="无法确定客户端 IP"):
        decide_module._resolve_context_ip(payload, _request_without_peer())


def test_missing_socket_peer_falls_back_to_reported_ip() -> None:
    """没有 socket peer 但客户端给了值时保留该值，好过让下游拿到 None。"""
    payload = DecisionRequest.model_validate(_sdk_body(ip="203.0.113.5"))
    resolved = decide_module._resolve_context_ip(payload, _request_without_peer())
    assert str(resolved.context.ip) == "203.0.113.5"


@pytest.mark.asyncio
async def test_service_rejects_unresolved_ip() -> None:
    """服务层兜底：None IP 若漏到这里必须炸，不能让 str(None) 污染缓存键。"""
    from src.application.services.decision_service import DecisionService

    service = DecisionService.__new__(DecisionService)  # 不需要依赖，只测前置断言
    payload = DecisionRequest.model_validate(_sdk_body())

    with pytest.raises(ValueError, match="未解析 IP"):
        await service.decide(payload)

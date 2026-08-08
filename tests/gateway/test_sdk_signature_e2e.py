"""SDK 签名与网关验签的端到端对接。

前面的 parity 测试锁的是「待签串构造一致」，这里锁的是「SDK 实际发出的请求
形状能过网关验签」——两件不同的事。历史上最容易出问题的不是编码规则本身，
而是**签名字段放错层级**：网关的 ``_signable_params`` 读的是 JSON body 的
**顶层**键，若 SDK 把 timestamp / nonce / sign 塞进 ``context`` 里面，
编码规则再对也验不过。
"""
from __future__ import annotations

import json
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
)

API_KEY = "ak_live_test"
SITE_SECRET = "sk_live_secret"
SITE_ID = 7


class _FakeRedis:
    def __init__(self) -> None:
        self.store = {
            f"fangyu:app_keys:{API_KEY}": json.dumps(
                {"site_id": SITE_ID, "site_secret": SITE_SECRET}
            )
        }

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


@dataclass
class _Settings:
    app_key_required: bool = True
    app_key_header: str = "X-App-Key"
    signature_required: bool = True
    signature_window: int = 300


class _MemoryNonceStore:
    def __init__(self) -> None:
        self.seen: set[tuple[int, str]] = set()

    async def claim(self, site_id: int, nonce: str) -> bool:
        entry = (site_id, nonce)
        if entry in self.seen:
            return False
        self.seen.add(entry)
        return True


def _build_app(nonce_store: _MemoryNonceStore | None = None) -> FastAPI:
    app = FastAPI()
    resolver = AppKeyResolver(_FakeRedis(), cache_ttl=0)
    app.add_middleware(
        AppKeyEnforcementMiddleware,
        resolver_provider=lambda: resolver,
        settings_provider=lambda: _Settings(),
        nonce_store_provider=(lambda: nonce_store) if nonce_store else None,
    )

    @app.post("/v2/decide")
    async def _decide(request: Request) -> dict[str, Any]:
        state = getattr(request.state, "resolved_app_key", None)
        return {"site_id": state.site_id, "verified": state.signature_verified}

    @app.post("/v2/sdk/heartbeat")
    async def _heartbeat(request: Request) -> dict[str, Any]:
        state = getattr(request.state, "resolved_app_key", None)
        return {"site_id": state.site_id, "verified": state.signature_verified}

    return app


def _sdk_decide_body(*, timestamp: int, nonce: str) -> dict[str, Any]:
    """复刻 SDK ``signBody`` 产出的请求体形状。

    注意 timestamp / nonce / sign 与 ``context`` **同级**，这正是网关
    ``_signable_params`` 期望的层级。
    """
    body: dict[str, Any] = {
        "context": {
            "siteId": SITE_ID,
            "ingress": "sdk",
            "fingerprint": "fp_abc123",
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "visitUrl": "https://shop.example.com/checkout?ref=a/b",
            "path": "/checkout",
            "method": "GET",
            "repeatKey": "_sd_0000",
            "repeatValue": "v_abc",
            "evercookieRestored": True,
            "behaviorEvents": [
                {"kind": "click", "clientTsMs": 1_700_000_000_000, "data": {"x": 10, "y": 20}},
                {"kind": "scroll", "clientTsMs": 1_700_000_000_500, "data": {"y": 300}},
            ],
        },
        "requireDetails": False,
        "timestamp": timestamp,
        "nonce": nonce,
    }
    body["sign"] = sign_params(body, SITE_SECRET)
    return body


@pytest.mark.asyncio
async def test_sdk_shaped_signed_request_passes_verification() -> None:
    """SDK 形状的已签请求能过验签。"""
    import time

    body = _sdk_decide_body(timestamp=int(time.time()), nonce=generate_nonce())
    transport = ASGITransport(app=_build_app(), client=("198.51.100.7", 1))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide", json=body, headers={"X-App-Key": API_KEY})

    assert resp.status_code == 200
    assert resp.json() == {"site_id": SITE_ID, "verified": True}


@pytest.mark.asyncio
async def test_nested_context_is_signed_as_canonical_json() -> None:
    """嵌套 context 参与签名时走键排序紧凑 JSON —— 重排键不应改变签名。"""
    import time

    ts = int(time.time())
    nonce = generate_nonce()
    body = _sdk_decide_body(timestamp=ts, nonce=nonce)

    # 把 context 的键顺序打乱后重算签名，结果必须一致
    shuffled = {
        "context": dict(reversed(list(body["context"].items()))),
        "requireDetails": body["requireDetails"],
        "timestamp": ts,
        "nonce": nonce,
    }
    assert sign_params(shuffled, SITE_SECRET) == body["sign"]


@pytest.mark.asyncio
async def test_tampered_context_fails_verification() -> None:
    """改了指纹但没重算签名 → 拒绝。这是签名保护画像可信度的核心断言。"""
    import time

    body = _sdk_decide_body(timestamp=int(time.time()), nonce=generate_nonce())
    body["context"]["fingerprint"] = "fp_forged"

    transport = ASGITransport(app=_build_app(), client=("198.51.100.7", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide", json=body, headers={"X-App-Key": API_KEY})

    assert resp.status_code == 401
    # 不告诉探测方是哪一步没过
    assert resp.json()["message"] == "API Key 无效或已失效"


@pytest.mark.asyncio
async def test_signature_fields_inside_context_are_not_accepted() -> None:
    """回归锁：签名字段放进 context 内层会验不过。

    这是最容易犯的接入错误，明确锁住能让 SDK 侧的层级不被无意改动。
    """
    import time

    inner = {
        "context": {
            "siteId": SITE_ID,
            "ingress": "sdk",
            "fingerprint": "fp_abc123",
            "userAgent": "Mozilla/5.0",
            "timestamp": int(time.time()),
            "nonce": generate_nonce(),
        },
    }
    inner["context"]["sign"] = sign_params(inner["context"], SITE_SECRET)

    transport = ASGITransport(app=_build_app(), client=("198.51.100.7", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide", json=inner, headers={"X-App-Key": API_KEY})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_replayed_nonce_rejected() -> None:
    import time

    store = _MemoryNonceStore()
    body = _sdk_decide_body(timestamp=int(time.time()), nonce=generate_nonce())
    app = _build_app(store)
    transport = ASGITransport(app=app, client=("198.51.100.7", 1))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v2/decide", json=body, headers={"X-App-Key": API_KEY})
        second = await client.post("/v2/decide", json=body, headers={"X-App-Key": API_KEY})

    assert first.status_code == 200
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_bad_signature_does_not_burn_nonce() -> None:
    """伪造签名不得消耗 nonce，否则可用来提前烧掉合法访客的 nonce。"""
    import time

    store = _MemoryNonceStore()
    nonce = generate_nonce()
    ts = int(time.time())

    forged = _sdk_decide_body(timestamp=ts, nonce=nonce)
    forged["sign"] = "0" * 64

    app = _build_app(store)
    transport = ASGITransport(app=app, client=("198.51.100.7", 1))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post("/v2/decide", json=forged, headers={"X-App-Key": API_KEY})
        # 同一个 nonce 配正确签名仍应可用
        good = _sdk_decide_body(timestamp=ts, nonce=nonce)
        ok = await client.post("/v2/decide", json=good, headers={"X-App-Key": API_KEY})

    assert bad.status_code == 401
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_stale_timestamp_rejected() -> None:
    import time

    body = _sdk_decide_body(timestamp=int(time.time()) - 400, nonce=generate_nonce())
    transport = ASGITransport(app=_build_app(), client=("198.51.100.7", 1))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/decide", json=body, headers={"X-App-Key": API_KEY})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sdk_heartbeat_signed_request_passes() -> None:
    """heartbeat 也在保护范围内，且 SDK 的签名形状同样适用。"""
    import time

    body: dict[str, Any] = {
        "siteId": SITE_ID,
        "fingerprint": "fp_abc123",
        "sdkVersion": "2.0.0",
        "behaviorEvents": [
            {"kind": "mouse_move", "clientTsMs": 1_700_000_000_000, "data": {"x": 1, "y": 2}}
        ],
        "timestamp": int(time.time()),
        "nonce": generate_nonce(),
    }
    body["sign"] = sign_params(body, SITE_SECRET)

    transport = ASGITransport(app=_build_app(), client=("198.51.100.7", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v2/sdk/heartbeat", json=body, headers={"X-App-Key": API_KEY}
        )

    assert resp.status_code == 200
    assert resp.json()["verified"] is True


@pytest.mark.asyncio
async def test_sdk_endpoints_reject_missing_api_key() -> None:
    """/v2/sdk/* 在保护范围内：无 Key 直接 401。"""
    transport = ASGITransport(app=_build_app(), client=("198.51.100.7", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v2/sdk/heartbeat", json={"siteId": SITE_ID})

    assert resp.status_code == 401

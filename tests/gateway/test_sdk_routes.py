"""/v2/sdk/* 路由测试。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fangyu_shared.exceptions import AuthenticationException
from fangyu_shared.schemas.clock import BehaviorEvent
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key
from src.interfaces.http.v2 import sdk as sdk_module
from src.interfaces.http.v2.sdk import SDK_VERSION, router as sdk_router


@dataclass
class _StubSettings:
    clock_enabled: bool = True
    whitelist_enabled: bool = True


class _RecordingClock:
    """记录 store_behavior 调用的 ClockRepository 替身。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    async def store_behavior(
        self,
        app_id: int,
        fingerprint: str,
        events: list[BehaviorEvent],
        *,
        now_ms: int,
    ) -> int:
        if self.fail:
            raise RuntimeError("redis down")
        self.calls.append(
            {
                "app_id": app_id,
                "fingerprint": fingerprint,
                "events": events,
                "now_ms": now_ms,
            }
        )
        return len(events)


@dataclass
class _Harness:
    app: FastAPI
    clock: _RecordingClock | None
    settings: _StubSettings = field(default_factory=_StubSettings)


def _build(
    *,
    app_id: int = 7,
    clock: _RecordingClock | None = None,
    settings: _StubSettings | None = None,
) -> _Harness:
    resolved_settings = settings or _StubSettings()
    app = FastAPI()
    app.include_router(sdk_router, prefix="/v2")

    app.dependency_overrides[require_app_key] = lambda: ResolvedAppKey(
        app_id=app_id, api_key="k"
    )
    app.dependency_overrides[sdk_module.get_gateway_settings] = lambda: resolved_settings
    app.dependency_overrides[sdk_module.get_clock_repository] = lambda: clock

    return _Harness(app=app, clock=clock, settings=resolved_settings)


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── /sdk/init ──


@pytest.mark.asyncio
async def test_init_returns_config_and_server_time() -> None:
    harness = _build()
    async with await _client(harness.app) as client:
        resp = await client.post("/v2/sdk/init", json={"appId": 7, "sdkVersion": "2.0.0"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["appId"] == 7
    assert data["sdkVersion"] == SDK_VERSION
    assert data["serverTimeMs"] > 0
    assert data["configVersion"]
    assert data["collectBehavior"] is True


@pytest.mark.asyncio
async def test_init_behavior_policy_matches_gateway_limit() -> None:
    """下发的 maxEvents 必须与网关单请求上限一致，否则 SDK 会攒出被截断的批次。"""
    from fangyu_shared.clock.windows import MAX_BEHAVIOR_EVENTS_PER_REQUEST

    harness = _build()
    async with await _client(harness.app) as client:
        resp = await client.post("/v2/sdk/init", json={"appId": 7})

    assert resp.json()["data"]["behavior"]["maxEvents"] == MAX_BEHAVIOR_EVENTS_PER_REQUEST


@pytest.mark.asyncio
async def test_init_disables_behavior_when_clock_off() -> None:
    harness = _build(settings=_StubSettings(clock_enabled=False))
    async with await _client(harness.app) as client:
        resp = await client.post("/v2/sdk/init", json={"appId": 7})

    data = resp.json()["data"]
    assert data["collectBehavior"] is False
    assert data["behavior"]["enabled"] is False


@pytest.mark.asyncio
async def test_init_accepts_omitted_app_id() -> None:
    """SDK 未自报 appId 时以 API Key 派生值为准。"""
    harness = _build(app_id=42)
    async with await _client(harness.app) as client:
        resp = await client.post("/v2/sdk/init", json={})

    assert resp.json()["data"]["appId"] == 42


@pytest.mark.asyncio
async def test_init_rejects_app_id_mismatch() -> None:
    """持有 A 站点 Key 不能冒充 B 站点。"""
    harness = _build(app_id=7)
    async with await _client(harness.app) as client:
        with pytest.raises(AuthenticationException):
            await client.post("/v2/sdk/init", json={"appId": 999})


@pytest.mark.asyncio
async def test_init_tolerates_client_version_mismatch() -> None:
    """旧版 SDK 仍然服务：硬拒会直接打断线上流量。"""
    harness = _build()
    async with await _client(harness.app) as client:
        resp = await client.post("/v2/sdk/init", json={"appId": 7, "sdkVersion": "1.0.0"})

    assert resp.status_code == 200
    assert resp.json()["data"]["sdkVersion"] == SDK_VERSION


# ── /sdk/status ──


@pytest.mark.asyncio
async def test_status_returns_same_config_version_as_init() -> None:
    """两个端点的版本口径必须一致，否则 SDK 会陷入无限重新 init。"""
    harness = _build()
    async with await _client(harness.app) as client:
        init = await client.post("/v2/sdk/init", json={"appId": 7})
        status = await client.get("/v2/sdk/status", params={"appId": 7})

    assert status.status_code == 200
    assert status.json()["data"]["configVersion"] == init.json()["data"]["configVersion"]


@pytest.mark.asyncio
async def test_status_version_changes_when_flags_change() -> None:
    on = _build(settings=_StubSettings(clock_enabled=True))
    off = _build(settings=_StubSettings(clock_enabled=False))

    async with await _client(on.app) as client:
        version_on = (await client.get("/v2/sdk/status", params={"appId": 7})).json()["data"][
            "configVersion"
        ]
    async with await _client(off.app) as client:
        version_off = (await client.get("/v2/sdk/status", params={"appId": 7})).json()["data"][
            "configVersion"
        ]

    assert version_on != version_off


@pytest.mark.asyncio
async def test_status_rejects_app_id_mismatch() -> None:
    harness = _build(app_id=7)
    async with await _client(harness.app) as client:
        with pytest.raises(AuthenticationException):
            await client.get("/v2/sdk/status", params={"appId": 999})


# ── /sdk/heartbeat ──


def _event(kind: str = "click", ts: int = 1_700_000_000_000) -> dict[str, Any]:
    return {"kind": kind, "clientTsMs": ts, "data": {"x": 10, "y": 20}}


@pytest.mark.asyncio
async def test_heartbeat_persists_behavior_events() -> None:
    clock = _RecordingClock()
    harness = _build(clock=clock)

    async with await _client(harness.app) as client:
        resp = await client.post(
            "/v2/sdk/heartbeat",
            json={"appId": 7, "fingerprint": "fp_abc", "behaviorEvents": [_event(), _event("scroll")]},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] == 2
    assert len(clock.calls) == 1
    assert clock.calls[0]["app_id"] == 7
    assert clock.calls[0]["fingerprint"] == "fp_abc"
    assert len(clock.calls[0]["events"]) == 2


@pytest.mark.asyncio
async def test_heartbeat_uses_key_derived_app_id_not_claimed() -> None:
    """入库用的 app_id 必须来自 API Key，不能采信请求体。"""
    clock = _RecordingClock()
    harness = _build(app_id=7, clock=clock)

    async with await _client(harness.app) as client:
        await client.post(
            "/v2/sdk/heartbeat",
            json={"fingerprint": "fp_abc", "behaviorEvents": [_event()]},
        )

    assert clock.calls[0]["app_id"] == 7


@pytest.mark.asyncio
async def test_heartbeat_drops_events_without_fingerprint() -> None:
    """缺指纹的事件无法归属访客，丢弃而非落成孤儿序列。"""
    clock = _RecordingClock()
    harness = _build(clock=clock)

    async with await _client(harness.app) as client:
        resp = await client.post(
            "/v2/sdk/heartbeat",
            json={"appId": 7, "fingerprint": "", "behaviorEvents": [_event()]},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] == 0
    assert clock.calls == []


@pytest.mark.asyncio
async def test_heartbeat_succeeds_without_events() -> None:
    """纯心跳（无事件）也要返回时间与版本，SDK 靠它校正时钟。"""
    clock = _RecordingClock()
    harness = _build(clock=clock)

    async with await _client(harness.app) as client:
        resp = await client.post("/v2/sdk/heartbeat", json={"appId": 7, "fingerprint": "fp"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["accepted"] == 0
    assert data["serverTimeMs"] > 0
    assert data["configVersion"]
    assert clock.calls == []


@pytest.mark.asyncio
async def test_heartbeat_survives_clock_failure() -> None:
    """行为入库失败不能让心跳整体失败——SDK 依赖响应校正时钟。"""
    harness = _build(clock=_RecordingClock(fail=True))

    async with await _client(harness.app) as client:
        resp = await client.post(
            "/v2/sdk/heartbeat",
            json={"appId": 7, "fingerprint": "fp", "behaviorEvents": [_event()]},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] == 0
    assert resp.json()["data"]["serverTimeMs"] > 0


@pytest.mark.asyncio
async def test_heartbeat_noop_when_clock_disabled() -> None:
    harness = _build(clock=None, settings=_StubSettings(clock_enabled=False))

    async with await _client(harness.app) as client:
        resp = await client.post(
            "/v2/sdk/heartbeat",
            json={"appId": 7, "fingerprint": "fp", "behaviorEvents": [_event()]},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] == 0


@pytest.mark.asyncio
async def test_heartbeat_rejects_oversized_batch() -> None:
    """超过网关单请求上限的批次由 pydantic 拦下，不进入 Redis。"""
    from fangyu_shared.clock.windows import MAX_BEHAVIOR_EVENTS_PER_REQUEST

    clock = _RecordingClock()
    harness = _build(clock=clock)
    events = [_event(ts=1_700_000_000_000 + i) for i in range(MAX_BEHAVIOR_EVENTS_PER_REQUEST + 1)]

    async with await _client(harness.app) as client:
        resp = await client.post(
            "/v2/sdk/heartbeat",
            json={"appId": 7, "fingerprint": "fp", "behaviorEvents": events},
        )

    assert resp.status_code == 422
    assert clock.calls == []


@pytest.mark.asyncio
async def test_heartbeat_rejects_unknown_behavior_kind() -> None:
    """枚举外的事件类型被拒，防止采集端随意扩张字段。"""
    clock = _RecordingClock()
    harness = _build(clock=clock)

    async with await _client(harness.app) as client:
        resp = await client.post(
            "/v2/sdk/heartbeat",
            json={
                "appId": 7,
                "fingerprint": "fp",
                "behaviorEvents": [{"kind": "keylogger_dump", "clientTsMs": 1, "data": {}}],
            },
        )

    assert resp.status_code == 422
    assert clock.calls == []


@pytest.mark.asyncio
async def test_heartbeat_rejects_app_id_mismatch() -> None:
    clock = _RecordingClock()
    harness = _build(app_id=7, clock=clock)

    async with await _client(harness.app) as client:
        with pytest.raises(AuthenticationException):
            await client.post(
                "/v2/sdk/heartbeat",
                json={"appId": 999, "fingerprint": "fp", "behaviorEvents": [_event()]},
            )

    assert clock.calls == []

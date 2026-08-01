"""威胁情报单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services import threat_intel_service as threat_intel_module
from src.application.services.threat_intel_service import ThreatIntelService


def _make_record(
    ip: str = "1.2.3.4",
    category: str = "malicious",
    severity: str = "medium",
    source: str = "manual",
    confidence: int = 80,
    is_active: bool = True,
) -> MagicMock:
    r = MagicMock()
    r.id = 1
    r.ip = ip
    r.category = category
    r.severity = severity
    r.source = source
    r.confidence = confidence
    r.description = ""
    r.is_active = is_active
    r.expires_at = None
    r.extra = None
    r.created_at = None
    r.updated_at = None
    return r


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_add_ip_calls_repo_and_sync(mock_session):
    record = _make_record()
    with (
        patch.object(threat_intel_module, "ThreatIntelRepository") as MockRepo,
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "add",
            new_callable=AsyncMock,
        ) as mock_sync_add,
    ):
        repo_instance = MockRepo.return_value
        repo_instance.upsert = AsyncMock(return_value=record)

        svc = ThreatIntelService(mock_session)
        result = await svc.add("1.2.3.4", category="malicious")

    assert result["ip"] == "1.2.3.4"
    assert result["category"] == "malicious"
    mock_sync_add.assert_awaited_once_with("1.2.3.4", "malicious")
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_ip_deactivates_and_syncs(mock_session):
    record = _make_record(category="proxy")
    with (
        patch.object(threat_intel_module, "ThreatIntelRepository") as MockRepo,
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "remove",
            new_callable=AsyncMock,
        ) as mock_sync_remove,
    ):
        repo_instance = MockRepo.return_value
        repo_instance.get = AsyncMock(return_value=record)
        repo_instance.deactivate = AsyncMock(return_value=True)

        svc = ThreatIntelService(mock_session)
        ok = await svc.remove("1.2.3.4")

    assert ok is True
    mock_sync_remove.assert_awaited_once_with("1.2.3.4", "proxy")


@pytest.mark.asyncio
async def test_remove_nonexistent_returns_false(mock_session):
    with (
        patch.object(threat_intel_module, "ThreatIntelRepository") as MockRepo,
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "remove",
            new_callable=AsyncMock,
        ),
    ):
        repo_instance = MockRepo.return_value
        repo_instance.get = AsyncMock(return_value=None)
        repo_instance.deactivate = AsyncMock(return_value=False)

        svc = ThreatIntelService(mock_session)
        ok = await svc.remove("9.9.9.9")

    assert ok is False


@pytest.mark.asyncio
async def test_list_active_returns_paginated(mock_session):
    records = [_make_record(ip=f"1.2.3.{i}") for i in range(3)]
    with patch.object(threat_intel_module, "ThreatIntelRepository") as MockRepo:
        repo_instance = MockRepo.return_value
        repo_instance.list_active = AsyncMock(return_value=(records, 3))

        svc = ThreatIntelService(mock_session)
        result = await svc.list_active(page=1, page_size=10)

    assert result["total"] == 3
    assert len(result["items"]) == 3
    assert result["items"][0]["ip"] == "1.2.3.0"


@pytest.mark.asyncio
async def test_bulk_import_calls_sync(mock_session):
    with (
        patch.object(threat_intel_module, "ThreatIntelRepository") as MockRepo,
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "full_sync",
            new_callable=AsyncMock,
        ),
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "stats",
            new_callable=AsyncMock,
            return_value={"total": 5, "key": "fangyu:threat_intel:all"},
        ),
        patch.object(ThreatIntelService, "sync_to_redis", new_callable=AsyncMock, return_value={"total": 5}),
    ):
        repo_instance = MockRepo.return_value
        repo_instance.bulk_insert = AsyncMock(return_value=2)
        repo_instance.list_active = AsyncMock(return_value=([], 0))
        repo_instance.list_all_active_ips = AsyncMock(return_value=[])

        svc = ThreatIntelService(mock_session)
        result = await svc.bulk_import([{"ip": "10.0.0.1"}, {"ip": "10.0.0.2"}])

    assert result["imported"] == 2


@pytest.mark.asyncio
async def test_sync_to_redis_groups_by_category(mock_session):
    records = [
        _make_record(ip="1.1.1.1", category="malicious"),
        _make_record(ip="2.2.2.2", category="proxy"),
        _make_record(ip="3.3.3.3", category="malicious"),
    ]
    with (
        patch.object(threat_intel_module, "ThreatIntelRepository") as MockRepo,
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "full_sync",
            new_callable=AsyncMock,
        ) as mock_full_sync,
        patch.object(
            threat_intel_module.ThreatIntelSync,
            "stats",
            new_callable=AsyncMock,
            return_value={"total": 3, "key": "fangyu:threat_intel:all"},
        ),
    ):
        repo_instance = MockRepo.return_value
        repo_instance.list_all_active_ips = AsyncMock(return_value=["1.1.1.1", "2.2.2.2", "3.3.3.3"])
        repo_instance.list_active = AsyncMock(return_value=(records, 3))

        svc = ThreatIntelService(mock_session)
        await svc.sync_to_redis()

    call_kwargs = mock_full_sync.call_args[0][0]
    assert set(call_kwargs["malicious"]) == {"1.1.1.1", "3.3.3.3"}
    assert call_kwargs["proxy"] == ["2.2.2.2"]

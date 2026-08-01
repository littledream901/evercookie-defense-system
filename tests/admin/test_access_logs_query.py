from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.infrastructure.clickhouse.access_log_query import AccessLogQueryService


class _FakeClickHouse:
    def __init__(self) -> None:
        self.calls = []

    async def fetch(self, sql: str, params: dict):
        self.calls.append((sql, params))
        return [{"request_id": "req-1", "app_id": 1, "verdict": "trusted"}]

    async def fetch_one(self, sql: str, params: dict):
        self.calls.append((sql, params))
        return {"total": 1}


def _service() -> tuple[AccessLogQueryService, _FakeClickHouse]:
    ch = _FakeClickHouse()
    return AccessLogQueryService(ch), ch  # type: ignore[arg-type]


def _window() -> tuple[datetime, datetime]:
    end = datetime.utcnow()
    return end - timedelta(days=1), end


@pytest.mark.asyncio
async def test_list_paged_builds_filters():
    service, ch = _service()
    start, end = _window()
    rows, total = await service.list_paged(
        app_id=1,
        start=start,
        end=end,
        filters={"request_id": "req-1", "ip": "1.1.1.1", "verdict": "trusted"},
        page=1,
        page_size=20,
    )
    assert total == 1
    assert rows[0]["request_id"] == "req-1"
    assert any("request_id = %(request_id)s" in sql for sql, _ in ch.calls)
    assert any(params.get("ip") == "1.1.1.1" for _, params in ch.calls)


@pytest.mark.asyncio
async def test_list_paged_ignores_unknown_filter_columns():
    """未在白名单内的列名必须被丢弃，防止列名拼接造成 SQL 注入。"""
    service, ch = _service()
    start, end = _window()
    await service.list_paged(
        app_id=1,
        start=start,
        end=end,
        filters={"ip = '1' OR 1=1 --": "x", "evil_col": "y"},
    )
    for sql, params in ch.calls:
        assert "OR 1=1" not in sql
        assert "evil_col" not in sql
        assert "evil_col" not in params


@pytest.mark.asyncio
async def test_list_paged_selects_parsed_columns():
    """UA / MMDB 解析结果必须在投影里，否则设备维度分析无法进行。"""
    service, ch = _service()
    start, end = _window()
    await service.list_paged(app_id=1, start=start, end=end)
    sql = ch.calls[0][0]
    for col in ("device_type", "os_name", "browser_name", "country", "asn", "connection_type"):
        assert col in sql


@pytest.mark.asyncio
async def test_list_paged_is_bot_filter():
    service, ch = _service()
    start, end = _window()
    await service.list_paged(app_id=1, start=start, end=end, is_bot=True)
    assert any(params.get("is_bot") == 1 for _, params in ch.calls)


@pytest.mark.asyncio
async def test_list_paged_offset_never_negative():
    service, ch = _service()
    start, end = _window()
    await service.list_paged(app_id=1, start=start, end=end, page=0, page_size=20)
    assert all(params.get("offset", 0) >= 0 for _, params in ch.calls)


@pytest.mark.asyncio
async def test_get_traces_queries_cold_table():
    service, ch = _service()
    await service.get_traces(app_id=1, request_id="req-1")
    assert "decision_traces" in ch.calls[0][0]


@pytest.mark.asyncio
async def test_stats_groups_by_disposition_layers():
    service, ch = _service()
    start, end = _window()
    await service.stats(app_id=1, start=start, end=end)
    sql = ch.calls[0][0]
    assert "verdict" in sql
    assert "mechanism" in sql
    assert "decided_by" in sql


@pytest.mark.asyncio
async def test_shadow_impact_uses_shadow_columns():
    service, ch = _service()
    start, end = _window()
    await service.shadow_impact(app_id=1, start=start, end=end)
    assert "shadow_rule_ids" in ch.calls[0][0]

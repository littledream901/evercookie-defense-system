"""ClickHouseClient.insert() SQL 构造回归测试。

覆盖本轮发现的 Bug：
insert() 曾把 SQL 写成 `VALUES (%s, %s, ...)`，但 aiochclient 的批量写入
协议要求 SQL 以 `VALUES` 结尾、行数据以位置参数传入。
带占位符的写法会被 ClickHouse 当字面量解析，报
`Code: 62. Cannot parse expression of type String here: %s`，
导致所有事件写入失败并全量进入死信队列——数据静默丢失。
"""
from __future__ import annotations

from typing import Any

import pytest

from fangyu_shared.clickhouse_manager.client import ClickHouseClient


class _RecordingChClient:
    """记录 execute() 收到的 SQL 与位置参数。"""

    def __init__(self) -> None:
        self.sql: str | None = None
        self.args: tuple[Any, ...] = ()

    async def execute(self, sql: str, *args: Any) -> None:
        self.sql = sql
        self.args = args


def _make_client() -> tuple[ClickHouseClient, _RecordingChClient]:
    rec = _RecordingChClient()
    client = ClickHouseClient(rec, config=None)  # type: ignore[arg-type]
    return client, rec


@pytest.mark.asyncio
async def test_insert_sql_has_no_percent_placeholders():
    """回归核心：SQL 里不能出现 %s，否则 ClickHouse 报 SYNTAX_ERROR。"""
    client, rec = _make_client()
    await client.insert("fangyu.decision_events", [{"event_id": "e1", "app_id": 1}])
    assert rec.sql is not None
    assert "%s" not in rec.sql, f"SQL 不应包含 %s 占位符: {rec.sql}"


@pytest.mark.asyncio
async def test_insert_sql_ends_with_values():
    """aiochclient 要求 SQL 以 VALUES 结尾。"""
    client, rec = _make_client()
    await client.insert("fangyu.decision_events", [{"event_id": "e1", "site_id": 1}])
    assert rec.sql is not None
    assert rec.sql.rstrip().endswith("VALUES"), f"SQL 应以 VALUES 结尾: {rec.sql}"


@pytest.mark.asyncio
async def test_insert_passes_rows_as_positional_tuples():
    """行数据必须作为位置参数传入，每行一个 tuple。"""
    client, rec = _make_client()
    rows = [
        {"event_id": "e1", "site_id": 1},
        {"event_id": "e2", "site_id": 2},
    ]
    await client.insert("fangyu.decision_events", rows)
    assert len(rec.args) == 2, "两行应产生两个位置参数"
    assert rec.args[0] == ("e1", 1)
    assert rec.args[1] == ("e2", 2)


@pytest.mark.asyncio
async def test_insert_column_order_matches_values():
    """列名顺序必须与 tuple 中值的顺序一致。"""
    client, rec = _make_client()
    await client.insert(
        "fangyu.decision_events",
        [{"event_id": "e1", "site_id": 7, "ip": "1.2.3.4"}],
    )
    assert rec.sql is not None
    assert "(event_id, site_id, ip)" in rec.sql
    assert rec.args[0] == ("e1", 7, "1.2.3.4")


@pytest.mark.asyncio
async def test_insert_missing_key_becomes_none():
    """后续行缺列时补 None，不能错位。"""
    client, rec = _make_client()
    rows = [
        {"event_id": "e1", "site_id": 1, "ip": "1.1.1.1"},
        {"event_id": "e2", "site_id": 2},
    ]
    await client.insert("fangyu.decision_events", rows)
    assert rec.args[1] == ("e2", 2, None)


@pytest.mark.asyncio
async def test_insert_empty_rows_is_noop():
    client, rec = _make_client()
    await client.insert("fangyu.decision_events", [])
    assert rec.sql is None, "空行列表不应发起任何写入"

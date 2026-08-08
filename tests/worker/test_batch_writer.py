"""BatchWriter 幂等与降级行为测试。

用 fake ClickHouse client 覆盖两种关键场景：
1. 批量成功 → 所有 message_id 都进 succeeded
2. 批量失败 → 降级为单条重试，脏数据入 failed
"""
from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.clickhouse_batch.batch_writer import BatchWriter


class _FakeCH:
    def __init__(self, *, fail_ids: set[str] | None = None, batch_fail: bool = False) -> None:
        self._fail_ids = fail_ids or set()
        self._batch_fail = batch_fail
        self.batch_calls = 0
        self.single_calls = 0
        self.inserted: list[dict[str, Any]] = []

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        if len(rows) > 1:
            self.batch_calls += 1
            if self._batch_fail:
                raise RuntimeError("batch insert broken")
            self.inserted.extend(rows)
            return

        self.single_calls += 1
        row = rows[0]
        if row.get("event_id") in self._fail_ids:
            raise RuntimeError(f"single row {row['event_id']} rejected")
        self.inserted.append(row)


def _row(event_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "site_id": 1,
        "schema_version": 1,
        "event_version": 1700000000000,
    }


@pytest.mark.asyncio
async def test_batch_write_success():
    ch = _FakeCH()
    writer = BatchWriter(ch, table="fangyu.decision_events")  # type: ignore[arg-type]
    rows = [_row("evt-1"), _row("evt-2")]
    result = await writer.write_batch(rows, message_ids=["m1", "m2"])
    assert result.succeeded_ids == ["m1", "m2"]
    assert result.failed_ids == []
    assert ch.batch_calls == 1
    assert ch.single_calls == 0


@pytest.mark.asyncio
async def test_batch_fails_then_single_fallback_isolates_bad_row():
    ch = _FakeCH(fail_ids={"evt-bad"}, batch_fail=True)
    writer = BatchWriter(
        ch,  # type: ignore[arg-type]
        table="fangyu.decision_events",
        max_retries=1,
        initial_backoff=0.01,
        max_backoff=0.02,
    )
    rows = [_row("evt-good"), _row("evt-bad")]
    result = await writer.write_batch(rows, message_ids=["ok", "bad"])
    assert "ok" in result.succeeded_ids
    assert len(result.failed_ids) == 1
    assert result.failed_ids[0][0] == "bad"
    # batch 尝试过 1 次，然后每条单独重试
    assert ch.batch_calls >= 1
    assert ch.single_calls == 2


@pytest.mark.asyncio
async def test_empty_input_returns_empty_result():
    ch = _FakeCH()
    writer = BatchWriter(ch, table="fangyu.decision_events")  # type: ignore[arg-type]
    result = await writer.write_batch([], message_ids=[])
    assert result.succeeded_ids == []
    assert result.failed_ids == []
    assert ch.batch_calls == 0

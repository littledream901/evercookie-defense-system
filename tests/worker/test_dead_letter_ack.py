"""DLQ 落盘与 ACK 的联动测试。

覆盖本轮修复的静默丢失路径：
DeadLetterHandler.publish_many() 曾吞掉 pipeline 异常只打日志，而 EventWriter
无条件把这些 message_id 放进 ack_ids。结果是 DLQ 写失败 → 消息被 ACK →
事件永久消失且无任何补偿手段。
"""
from __future__ import annotations

from typing import Any

import pytest
from src.application.writers.event_writer import EventWriter
from src.domain.event.stream_message import StreamMessage
from src.infrastructure.dead_letter.dead_letter import DeadLetterHandler


class _FakePipeline:
    """按 message_id 决定每条 XADD 是成功还是返回异常。"""

    def __init__(self, fail_ids: set[str], *, explode: bool = False) -> None:
        self._fail_ids = fail_ids
        self._explode = explode
        self._queued: list[str] = []

    def xadd(self, *, name: str, fields: dict[str, Any], **kwargs: Any) -> None:
        self._queued.append(fields["message_id"])

    async def execute(self, raise_on_error: bool = True) -> list[Any]:
        if self._explode:
            raise ConnectionError("redis gone")
        return [
            RuntimeError(f"xadd rejected {mid}") if mid in self._fail_ids else b"1-1"
            for mid in self._queued
        ]


class _FakeRedis:
    def __init__(self, fail_ids: set[str] | None = None, *, explode: bool = False) -> None:
        self._fail_ids = fail_ids or set()
        self._explode = explode

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        return _FakePipeline(self._fail_ids, explode=self._explode)


def _items(*mids: str) -> list[tuple[str, dict[str, Any], str]]:
    return [(mid, {"eventId": mid}, "transform_error:boom") for mid in mids]


# ---------- publish_many 落盘报告 ----------

@pytest.mark.asyncio
async def test_publish_many_reports_all_persisted():
    handler = DeadLetterHandler(_FakeRedis())  # type: ignore[arg-type]
    persisted = await handler.publish_many(_items("m1", "m2"))
    assert persisted == {"m1", "m2"}


@pytest.mark.asyncio
async def test_publish_many_excludes_failed_entries():
    """个别 XADD 失败时只报成功的那部分，不能整批算成功。"""
    handler = DeadLetterHandler(_FakeRedis({"m2"}))  # type: ignore[arg-type]
    persisted = await handler.publish_many(_items("m1", "m2", "m3"))
    assert persisted == {"m1", "m3"}


@pytest.mark.asyncio
async def test_publish_many_returns_empty_when_pipeline_dies():
    handler = DeadLetterHandler(_FakeRedis(explode=True))  # type: ignore[arg-type]
    persisted = await handler.publish_many(_items("m1", "m2"))
    assert persisted == set()


@pytest.mark.asyncio
async def test_publish_many_empty_input():
    handler = DeadLetterHandler(_FakeRedis())  # type: ignore[arg-type]
    assert await handler.publish_many([]) == set()


# ---------- EventWriter 只 ACK 已落盘的死信 ----------

class _NoopBatchWriter:
    """不产生行时不会被调用；这里只为满足依赖。"""

    async def write_batch(self, rows, *, message_ids):
        raise AssertionError("本用例不应触发批量写入")


def _bad_msg(mid: str) -> StreamMessage:
    # 缺 eventId → transform 阶段判为 invalid → 走 DLQ 路径
    return StreamMessage(stream="s", message_id=mid, payload={"appId": 1})


@pytest.mark.asyncio
async def test_invalid_events_acked_only_after_dlq_persist():
    from src.application.transformers.event_transformer import EventTransformer

    writer = EventWriter(
        transformer=EventTransformer(),
        batch_writer=_NoopBatchWriter(),  # type: ignore[arg-type]
        dead_letter=DeadLetterHandler(_FakeRedis()),  # type: ignore[arg-type]
    )
    outcome = await writer.handle([_bad_msg("m1"), _bad_msg("m2")])
    assert sorted(outcome.ack_ids) == ["m1", "m2"]
    assert outcome.dead_letter_count == 2


@pytest.mark.asyncio
async def test_unpersisted_dead_letters_are_not_acked():
    """回归核心：DLQ 写失败的消息必须保持 pending，绝不能被 ACK。"""
    from src.application.transformers.event_transformer import EventTransformer

    writer = EventWriter(
        transformer=EventTransformer(),
        batch_writer=_NoopBatchWriter(),  # type: ignore[arg-type]
        dead_letter=DeadLetterHandler(_FakeRedis({"m2"})),  # type: ignore[arg-type]
    )
    outcome = await writer.handle([_bad_msg("m1"), _bad_msg("m2")])
    assert outcome.ack_ids == ["m1"]
    assert "m2" not in outcome.ack_ids
    assert outcome.dead_letter_count == 1


@pytest.mark.asyncio
async def test_nothing_acked_when_dlq_completely_unavailable():
    from src.application.transformers.event_transformer import EventTransformer

    writer = EventWriter(
        transformer=EventTransformer(),
        batch_writer=_NoopBatchWriter(),  # type: ignore[arg-type]
        dead_letter=DeadLetterHandler(_FakeRedis(explode=True)),  # type: ignore[arg-type]
    )
    outcome = await writer.handle([_bad_msg("m1"), _bad_msg("m2")])
    assert outcome.ack_ids == []
    assert outcome.dead_letter_count == 0

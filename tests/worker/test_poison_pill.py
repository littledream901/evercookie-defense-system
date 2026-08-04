"""毒丸熔断与消费者命名测试。

覆盖本轮修复的两个缺陷：
1. claim_stale() 曾把 delivered_count 硬编码为 2，真实投递次数拿不到，
   「投递 N 次后放弃」的熔断无从实现——稳定打挂 ClickHouse 的消息会被无限重投。
2. consumer_name 曾硬编码 "worker-1"，多副本共用同名会互相抢占 pending 消息。
"""
from __future__ import annotations

from typing import Any

import orjson
import pytest
from src.infrastructure.stream.consumer import StreamConsumer, StreamConsumerConfig


def _cfg(**kw: Any) -> StreamConsumerConfig:
    base = {
        "stream_name": "s",
        "group_name": "g",
        "consumer_name": "c",
        "max_delivery_count": 5,
    }
    base.update(kw)
    return StreamConsumerConfig(**base)  # type: ignore[arg-type]


class _FakeRedis:
    """最小 XAUTOCLAIM / XPENDING 替身。"""

    def __init__(
        self,
        entries: list[tuple[str, dict[str, str]]],
        counts: dict[str, int],
        *,
        pending_raises: bool = False,
    ) -> None:
        self._entries = entries
        self._counts = counts
        self._pending_raises = pending_raises
        self.acked: list[str] = []

    async def xautoclaim(self, **kwargs: Any) -> tuple:
        return ("0-0", self._entries, [])

    async def xpending_range(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self._pending_raises:
            raise ConnectionError("xpending unavailable")
        return [
            {"message_id": mid, "times_delivered": n} for mid, n in self._counts.items()
        ]

    async def xack(self, *args: Any) -> int:
        self.acked.extend(args[2:])
        return len(args) - 2


class _RecordingDLQ:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.received: list[tuple[str, dict, str]] = []

    async def publish_many(self, items: list[tuple[str, dict, str]]) -> set[str]:
        self.received.extend(items)
        if self._fail:
            return set()
        return {mid for mid, _, _ in items}


def _entry(mid: str) -> tuple[str, dict[str, str]]:
    return (mid, {"payload": orjson.dumps({"eventId": mid}).decode()})


# ---------- 真实投递次数 ----------

@pytest.mark.asyncio
async def test_claim_stale_reads_real_delivery_count():
    """不再硬编码 2，delivered_count 必须来自 XPENDING。"""
    redis = _FakeRedis([_entry("1-1"), _entry("2-1")], {"1-1": 3, "2-1": 1})
    consumer = StreamConsumer(redis, _cfg())  # type: ignore[arg-type]
    msgs = await consumer.claim_stale()
    by_id = {m.message_id: m.delivered_count for m in msgs}
    assert by_id == {"1-1": 3, "2-1": 1}


@pytest.mark.asyncio
async def test_delivery_count_missing_defaults_to_one():
    """XPENDING 没返回该条时按首次投递处理，宁可多重试也不误判为毒丸。"""
    redis = _FakeRedis([_entry("9-1")], {})
    consumer = StreamConsumer(redis, _cfg())  # type: ignore[arg-type]
    msgs = await consumer.claim_stale()
    assert [m.delivered_count for m in msgs] == [1]


@pytest.mark.asyncio
async def test_xpending_error_fails_open():
    """读投递次数失败不应阻断消费：消息照常返回，按首次投递处理。"""
    redis = _FakeRedis([_entry("1-1")], {"1-1": 99}, pending_raises=True)
    consumer = StreamConsumer(redis, _cfg())  # type: ignore[arg-type]
    msgs = await consumer.claim_stale()
    assert len(msgs) == 1
    assert msgs[0].delivered_count == 1


# ---------- 毒丸熔断 ----------

@pytest.mark.asyncio
async def test_over_threshold_message_routed_to_dlq_and_acked():
    redis = _FakeRedis([_entry("1-1"), _entry("2-1")], {"1-1": 6, "2-1": 2})
    dlq = _RecordingDLQ()
    consumer = StreamConsumer(redis, _cfg(max_delivery_count=5), dead_letter=dlq)  # type: ignore[arg-type]
    msgs = await consumer.claim_stale()

    # 毒丸不再返回给业务处理
    assert [m.message_id for m in msgs] == ["2-1"]
    # 已转入 DLQ 并 ACK，从重试环里摘出
    assert [mid for mid, _, _ in dlq.received] == ["1-1"]
    assert "max_delivery_exceeded:6" in dlq.received[0][2]
    assert redis.acked == ["1-1"]


@pytest.mark.asyncio
async def test_at_threshold_still_retried():
    """等于上限时仍然重试，只有严格超过才熔断。"""
    redis = _FakeRedis([_entry("1-1")], {"1-1": 5})
    dlq = _RecordingDLQ()
    consumer = StreamConsumer(redis, _cfg(max_delivery_count=5), dead_letter=dlq)  # type: ignore[arg-type]
    msgs = await consumer.claim_stale()
    assert [m.message_id for m in msgs] == ["1-1"]
    assert dlq.received == []
    assert redis.acked == []


@pytest.mark.asyncio
async def test_poison_not_acked_when_dlq_write_fails():
    """DLQ 没落盘就不能 ACK，否则又变成静默丢弃。"""
    redis = _FakeRedis([_entry("1-1")], {"1-1": 9})
    dlq = _RecordingDLQ(fail=True)
    consumer = StreamConsumer(redis, _cfg(max_delivery_count=5), dead_letter=dlq)  # type: ignore[arg-type]
    await consumer.claim_stale()
    assert redis.acked == []


@pytest.mark.asyncio
async def test_poison_kept_pending_when_no_dlq_configured():
    """未配置 DLQ 时保持原行为，不 ACK（ACK 等于丢数据）。"""
    redis = _FakeRedis([_entry("1-1")], {"1-1": 9})
    consumer = StreamConsumer(redis, _cfg(max_delivery_count=5))  # type: ignore[arg-type]
    msgs = await consumer.claim_stale()
    assert msgs == []
    assert redis.acked == []


# ---------- 消费者名唯一性 ----------

def test_consumer_name_unique_per_process():
    import os
    import socket

    from src.config import WorkerSettings

    name = WorkerSettings().consumer_name
    assert name != "worker-1", "硬编码名会让多副本互抢 pending 消息"
    assert socket.gethostname() in name
    assert str(os.getpid()) in name


def test_consumer_name_env_override(monkeypatch):
    from src.config import WorkerSettings

    monkeypatch.setenv("WORKER_CONSUMER_NAME", "explicit-worker-7")
    assert WorkerSettings().consumer_name == "explicit-worker-7"


def test_max_delivery_count_default():
    from src.config import WorkerSettings

    assert WorkerSettings().max_delivery_count == 5

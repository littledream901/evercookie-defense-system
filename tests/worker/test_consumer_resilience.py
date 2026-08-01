"""DecisionConsumer 韧性回归测试。

覆盖本轮发现的 Bug：
consumer.read() 的调用曾裸露在 try 保护之外，Redis 一次读超时
（stream_block_ms 与客户端 socket_timeout 相等时必然发生）
就会让整个 worker 进程退出，消费彻底停止。
"""
from __future__ import annotations

import asyncio

import pytest

from src.application.consumers.decision_consumer import DecisionConsumer


class _Outcome:
    def __init__(self) -> None:
        self.ack_ids: list[str] = []
        self.dead_letter_count = 0


class _FakeWriter:
    def __init__(self) -> None:
        self.handled: list[list] = []

    async def handle(self, batch):
        self.handled.append(batch)
        return _Outcome()


class _FlakyConsumer:
    """前 N 次 read 抛异常，之后返回一批数据。"""

    def __init__(self, fail_times: int, exc: Exception) -> None:
        self._fail_times = fail_times
        self._exc = exc
        self.read_calls = 0
        self.group_ready = False

    async def ensure_group(self) -> None:
        self.group_ready = True

    async def read(self):
        self.read_calls += 1
        if self.read_calls <= self._fail_times:
            raise self._exc
        # 只投递一批，之后返回空，避免测试里的无限循环
        if self.read_calls == self._fail_times + 1:
            return [_msg("m1")]
        return []

    async def ack(self, ids):
        return len(ids)

    async def claim_stale(self, *a, **kw):
        return []


class _Msg:
    def __init__(self, mid: str) -> None:
        self.message_id = mid
        self.traceparent = None


def _msg(mid: str) -> _Msg:
    return _Msg(mid)


@pytest.mark.asyncio
async def test_read_timeout_does_not_kill_loop():
    """回归核心：读超时后应退避重试，而不是让 run() 抛出。"""
    import redis.exceptions

    consumer = _FlakyConsumer(
        fail_times=2, exc=redis.exceptions.TimeoutError("Timeout reading from redis")
    )
    writer = _FakeWriter()
    dc = DecisionConsumer(
        stream_consumer=consumer,  # type: ignore[arg-type]
        event_writer=writer,  # type: ignore[arg-type]
        idle_sleep_seconds=0.001,
        claim_interval_seconds=3600,
        read_error_backoff_seconds=0.001,
    )

    task = asyncio.create_task(dc.run())
    for _ in range(200):
        await asyncio.sleep(0.005)
        if writer.handled:
            break
    dc._stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert consumer.read_calls > 2, "超时后应继续重试读取"
    assert writer.handled, "恢复后应成功处理批次"


@pytest.mark.asyncio
async def test_generic_read_error_also_retried():
    """任意读取异常（连接重置、主从切换）都应重试。"""
    consumer = _FlakyConsumer(fail_times=1, exc=ConnectionError("connection reset"))
    writer = _FakeWriter()
    dc = DecisionConsumer(
        stream_consumer=consumer,  # type: ignore[arg-type]
        event_writer=writer,  # type: ignore[arg-type]
        idle_sleep_seconds=0.001,
        claim_interval_seconds=3600,
        read_error_backoff_seconds=0.001,
    )

    task = asyncio.create_task(dc.run())
    for _ in range(200):
        await asyncio.sleep(0.005)
        if writer.handled:
            break
    dc._stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert writer.handled, "连接错误恢复后应继续消费"


def test_stream_block_ms_below_socket_timeout():
    """配置约束：阻塞读时长必须小于 Redis socket_timeout，否则必然超时。"""
    from fangyu_shared.redis_manager.config import RedisConfig

    from src.config import WorkerSettings

    worker_block_seconds = WorkerSettings().stream_block_ms / 1000
    socket_timeout = RedisConfig().socket_timeout
    assert worker_block_seconds < socket_timeout, (
        f"stream_block_ms={worker_block_seconds}s 必须小于 "
        f"socket_timeout={socket_timeout}s，否则阻塞读会稳定触发客户端超时"
    )

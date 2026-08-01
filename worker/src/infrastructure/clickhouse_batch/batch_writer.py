"""ClickHouse 批量写入器。

设计目标：
- 累积到 batch_size 或超过 flush 间隔时批量写入
- 单条失败时降级为逐条写入，隔离脏数据
- 返回成功/失败清单，便于上层做 ACK 与 DLQ 处理
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from fangyu_shared.clickhouse_manager import ClickHouseClient
from fangyu_shared.logging import get_logger
from fangyu_shared.metrics import stream_events_processed_total

_logger = get_logger("worker.batch_writer")


@dataclass(slots=True)
class WriteResult:
    """写入结果，附带失败清单。"""

    succeeded_ids: list[str] = field(default_factory=list)
    failed_ids: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.succeeded_ids) + len(self.failed_ids)


class BatchWriter:
    def __init__(
        self,
        client: ClickHouseClient,
        *,
        table: str,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        max_backoff: float = 10.0,
    ) -> None:
        self._client = client
        self._table = table
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._lock = asyncio.Lock()

    async def write_batch(
        self,
        rows: list[dict[str, Any]],
        *,
        message_ids: list[str],
    ) -> WriteResult:
        assert len(rows) == len(message_ids), "rows 与 message_ids 长度必须一致"
        if not rows:
            return WriteResult()

        async with self._lock:
            try:
                await self._insert_with_retry(rows)
                stream_events_processed_total.labels(
                    stream="decision",
                    consumer_group="worker",
                    status="success",
                ).inc(len(rows))
                return WriteResult(succeeded_ids=list(message_ids))
            except Exception as batch_exc:
                _logger.warning(
                    "batch_write_failed_fallback_to_single",
                    error=str(batch_exc),
                    batch_size=len(rows),
                )
                return await self._degrade_to_single(rows, message_ids)

    async def _insert_with_retry(self, rows: list[dict[str, Any]]) -> None:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(
                multiplier=self._initial_backoff,
                min=self._initial_backoff,
                max=self._max_backoff,
            ),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                await self._client.insert(self._table, rows)

    async def _degrade_to_single(
        self,
        rows: list[dict[str, Any]],
        message_ids: list[str],
    ) -> WriteResult:
        result = WriteResult()
        for row, mid in zip(rows, message_ids, strict=True):
            try:
                await self._client.insert(self._table, [row])
                result.succeeded_ids.append(mid)
                stream_events_processed_total.labels(
                    stream="decision",
                    consumer_group="worker",
                    status="success",
                ).inc()
            except Exception as exc:
                result.failed_ids.append((mid, str(exc)))
                stream_events_processed_total.labels(
                    stream="decision",
                    consumer_group="worker",
                    status="failure",
                ).inc()
                _logger.error("single_write_failed", message_id=mid, error=str(exc))
        return result

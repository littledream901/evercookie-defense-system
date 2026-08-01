"""决策事件消费者。

主循环流程：
1. 从 Stream 拉取批次（先 pending 再新消息）
2. 转换 + 批量写入 ClickHouse
3. 失败进入 DLQ，成功统一 ACK
4. 定期抢占 stale pending
"""

from __future__ import annotations

import asyncio

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from fangyu_shared.logging import bind_request_context, clear_request_context, get_logger
from fangyu_shared.tracing import extract_context, get_tracer

from src.application.writers.event_writer import EventWriter
from src.infrastructure.stream.consumer import StreamConsumer

_logger = get_logger("worker.decision_consumer")
_tracer = get_tracer("worker.decision_consumer")


class DecisionConsumer:
    def __init__(
        self,
        *,
        stream_consumer: StreamConsumer,
        event_writer: EventWriter,
        idle_sleep_seconds: float = 0.05,
        claim_interval_seconds: float = 30.0,
        read_error_backoff_seconds: float = 1.0,
    ) -> None:
        self._consumer = stream_consumer
        self._writer = event_writer
        self._idle_sleep = idle_sleep_seconds
        self._claim_interval = claim_interval_seconds
        self._read_error_backoff = read_error_backoff_seconds
        self._stop = asyncio.Event()

    async def run(self) -> None:
        await self._consumer.ensure_group()
        _logger.info("decision_consumer_started")
        claim_task = asyncio.create_task(self._claim_loop())
        try:
            while not self._stop.is_set():
                try:
                    batch = await self._consumer.read()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # 读取失败（Redis 超时、连接抖动、主从切换）不应终止消费循环：
                    # 退避后重试，让 worker 在基础设施恢复后自动继续消费。
                    _logger.warning("stream_read_failed_retrying", error=str(exc))
                    await asyncio.sleep(self._read_error_backoff)
                    continue

                if not batch:
                    await asyncio.sleep(self._idle_sleep)
                    continue
                await self._process_batch(batch)
        finally:
            claim_task.cancel()
            try:
                await claim_task
            except asyncio.CancelledError:
                pass
            _logger.info("decision_consumer_stopped")

    async def _process_batch(self, batch: list) -> None:
        rid = bind_request_context(batch_size=len(batch))
        first = batch[0] if batch else None
        traceparent_carrier = {"traceparent": first.traceparent} if (first and first.traceparent) else {}
        parent_ctx = extract_context(traceparent_carrier) if traceparent_carrier else None

        span_kwargs: dict = {
            "name": "worker.process_batch",
            "kind": SpanKind.CONSUMER,
            "attributes": {
                "messaging.batch.size": len(batch),
                "messaging.system": "redis",
            },
        }
        if parent_ctx is not None:
            span_kwargs["context"] = parent_ctx

        with _tracer.start_as_current_span(**span_kwargs) as span:
            try:
                outcome = await self._writer.handle(batch)
                if outcome.ack_ids:
                    acked = await self._consumer.ack(outcome.ack_ids)
                    span.set_attribute("messaging.acked", acked)
                    span.set_attribute("messaging.dlq", outcome.dead_letter_count)
                    _logger.info(
                        "batch_processed",
                        request_id=rid,
                        batch=len(batch),
                        acked=acked,
                        dlq=outcome.dead_letter_count,
                    )
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                _logger.exception("batch_processing_error", error=str(exc))
            finally:
                clear_request_context()

    async def _claim_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.sleep(self._claim_interval)
                stale = await self._consumer.claim_stale()
                if stale:
                    _logger.info("claimed_stale_messages", count=len(stale))
                    await self._process_batch(stale)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                _logger.warning("claim_loop_error", error=str(exc))

    def request_stop(self) -> None:
        self._stop.set()

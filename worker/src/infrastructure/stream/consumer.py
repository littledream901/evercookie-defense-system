"""Redis Stream 消费者。

功能：
- 使用 XREADGROUP 拉取消息（有 pending 时优先重放）
- 自动创建消费者组与 Stream（幂等）
- 支持 XCLAIM 抢回长时间未 ACK 的消息
- 输出统一的 StreamMessage 值对象
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import orjson
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from fangyu_shared.logging import get_logger
from fangyu_shared.metrics import stream_events_consumed_total, stream_lag

from src.domain.event.stream_message import StreamMessage

_logger = get_logger("worker.stream_consumer")


@dataclass(frozen=True, slots=True)
class StreamConsumerConfig:
    stream_name: str
    group_name: str
    consumer_name: str
    batch_size: int = 200
    block_ms: int = 5000
    claim_min_idle_ms: int = 60_000
    start_id: str = "$"


class StreamConsumer:
    def __init__(self, redis: Redis, config: StreamConsumerConfig) -> None:
        self._redis = redis
        self._config = config

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                id=self._config.start_id,
                mkstream=True,
            )
            _logger.info(
                "consumer_group_created",
                stream=self._config.stream_name,
                group=self._config.group_name,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read(self) -> list[StreamMessage]:
        """先取 pending，再取新消息。"""
        pending = await self._read_pending()
        if pending:
            await self._update_lag()
            return pending
        messages = await self._read_new()
        await self._update_lag()
        return messages

    async def _update_lag(self) -> None:
        try:
            info = await self._redis.xpending(
                self._config.stream_name,
                self._config.group_name,
            )
            pending_count: int = info.get("pending", 0) if isinstance(info, dict) else (info[0] if info else 0)
        except Exception:
            pending_count = 0
        stream_lag.labels(
            stream=self._config.stream_name,
            consumer_group=self._config.group_name,
        ).set(pending_count)

    async def _read_pending(self) -> list[StreamMessage]:
        raw = await self._redis.xreadgroup(
            groupname=self._config.group_name,
            consumername=self._config.consumer_name,
            streams={self._config.stream_name: "0"},
            count=self._config.batch_size,
        )
        return self._parse(raw)

    async def _read_new(self) -> list[StreamMessage]:
        raw = await self._redis.xreadgroup(
            groupname=self._config.group_name,
            consumername=self._config.consumer_name,
            streams={self._config.stream_name: ">"},
            count=self._config.batch_size,
            block=self._config.block_ms,
        )
        return self._parse(raw)

    def _parse(self, raw: list | None) -> list[StreamMessage]:
        if not raw:
            return []
        messages: list[StreamMessage] = []
        for _stream, entries in raw:
            for message_id, fields in entries:
                payload_raw = fields.get("payload") if isinstance(fields, dict) else None
                if payload_raw is None:
                    continue
                try:
                    payload = orjson.loads(payload_raw)
                except orjson.JSONDecodeError:
                    _logger.warning("stream_payload_invalid_json", message_id=message_id)
                    continue
                traceparent = fields.get("traceparent") if isinstance(fields, dict) else None
                if isinstance(traceparent, bytes):
                    traceparent = traceparent.decode()
                messages.append(
                    StreamMessage(
                        stream=self._config.stream_name,
                        message_id=message_id,
                        payload=payload,
                        traceparent=traceparent,
                    )
                )
        if messages:
            stream_events_consumed_total.labels(
                stream=self._config.stream_name,
                consumer_group=self._config.group_name,
            ).inc(len(messages))
        return messages

    async def ack(self, message_ids: list[str]) -> int:
        if not message_ids:
            return 0
        return int(await self._redis.xack(
            self._config.stream_name,
            self._config.group_name,
            *message_ids,
        ))

    async def claim_stale(self, count: int = 50) -> list[StreamMessage]:
        """抢回长期未 ACK 的消息，防止消费者卡死。"""
        try:
            reply = await self._redis.xautoclaim(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                consumername=self._config.consumer_name,
                min_idle_time=self._config.claim_min_idle_ms,
                count=count,
            )
        except ResponseError as exc:
            _logger.warning("xautoclaim_failed", error=str(exc))
            return []
        # reply: (next_id, [(id, fields), ...], deleted_ids)
        entries = reply[1] if isinstance(reply, (tuple, list)) and len(reply) >= 2 else []
        parsed: list[StreamMessage] = []
        for message_id, fields in entries or []:
            payload_raw = fields.get("payload") if isinstance(fields, dict) else None
            if payload_raw is None:
                continue
            try:
                payload = orjson.loads(payload_raw)
            except orjson.JSONDecodeError:
                continue
            parsed.append(
                StreamMessage(
                    stream=self._config.stream_name,
                    message_id=message_id,
                    payload=payload,
                    delivered_count=2,
                )
            )
        return parsed

    async def iterate(self) -> AsyncIterator[list[StreamMessage]]:
        await self.ensure_group()
        while True:
            batch = await self.read()
            if batch:
                yield batch

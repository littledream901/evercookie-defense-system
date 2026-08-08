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
from src.infrastructure.dead_letter.dead_letter import DeadLetterHandler

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
    max_delivery_count: int = 5


class StreamConsumer:
    def __init__(
        self,
        redis: Redis,
        config: StreamConsumerConfig,
        *,
        dead_letter: DeadLetterHandler | None = None,
    ) -> None:
        self._redis = redis
        self._config = config
        self._dead_letter = dead_letter

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

    async def _delivery_counts(self, message_ids: list[str]) -> dict[str, int]:
        """读取指定消息的真实投递次数。

        XPENDING 的 range 形式（start/end/count）才返回每条消息的
        delivery counter；summary 形式只给总数。拿不到真实次数就无法判断
        「重试了几轮」，毒丸熔断也就无从下手。

        按 consumer 过滤而非按 ID 区间取：Stream ID 是 ``<毫秒>-<序号>`` 字符串，
        字典序与时间序不一致（``"10-0" < "9-0"``），用 min()/max() 拼区间会漏消息。
        刚被 XAUTOCLAIM 抢到本消费者名下，按 consumer 过滤即可覆盖这批。

        本消费者名下 pending 数超过 count 时可能取不全，个别消息按首次投递处理，
        熔断推迟到下一轮 claim。这只影响熔断时机，不会误判或丢消息。
        """
        if not message_ids:
            return {}
        try:
            entries = await self._redis.xpending_range(
                name=self._config.stream_name,
                groupname=self._config.group_name,
                min="-",
                max="+",
                count=len(message_ids),
                consumername=self._config.consumer_name,
            )
        except Exception as exc:
            # fail-open：读不到投递次数时不阻断消费，退回按「首次投递」处理。
            _logger.warning("xpending_range_failed", error=str(exc))
            return {}
        counts: dict[str, int] = {}
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            mid = entry.get("message_id")
            if isinstance(mid, bytes):
                mid = mid.decode()
            if mid is None:
                continue
            counts[str(mid)] = int(entry.get("times_delivered") or 1)
        return counts

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
        decoded: list[tuple[str, dict]] = []
        for message_id, fields in entries or []:
            payload_raw = fields.get("payload") if isinstance(fields, dict) else None
            if payload_raw is None:
                continue
            try:
                payload = orjson.loads(payload_raw)
            except orjson.JSONDecodeError:
                continue
            decoded.append((message_id, payload))

        if not decoded:
            return []

        counts = await self._delivery_counts([mid for mid, _ in decoded])
        parsed: list[StreamMessage] = []
        poison: list[tuple[str, dict, str]] = []
        for message_id, payload in decoded:
            # 缺失时按 1 处理（fail-open）：宁可多重试一轮，也不要凭猜测丢消息。
            delivered = counts.get(message_id, 1)
            if delivered > self._config.max_delivery_count:
                poison.append(
                    (message_id, payload, f"max_delivery_exceeded:{delivered}")
                )
                continue
            parsed.append(
                StreamMessage(
                    stream=self._config.stream_name,
                    message_id=message_id,
                    payload=payload,
                    delivered_count=delivered,
                )
            )

        if poison:
            await self._handle_poison(poison)
        return parsed

    async def _handle_poison(self, poison: list[tuple[str, dict, str]]) -> None:
        """投递次数超限的消息转 DLQ 并 ACK，把它们从重试环里摘出来。"""
        if self._dead_letter is None:
            # 没配 DLQ 时保持原行为继续重试：这里 ACK 就等于静默丢弃。
            _logger.warning(
                "poison_message_no_dead_letter_configured",
                count=len(poison),
            )
            return
        persisted = await self._dead_letter.publish_many(poison)
        # 同 EventWriter：只 ACK 确实落入 DLQ 的，未落盘的留在 pending 下轮再来。
        if persisted:
            await self.ack([mid for mid, _, _ in poison if mid in persisted])
        _logger.error(
            "poison_messages_dead_lettered",
            count=len(persisted),
            not_persisted=len(poison) - len(persisted),
            max_delivery_count=self._config.max_delivery_count,
        )

    async def iterate(self) -> AsyncIterator[list[StreamMessage]]:
        await self.ensure_group()
        while True:
            batch = await self.read()
            if batch:
                yield batch

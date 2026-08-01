"""死信队列处理器。

写入独立的 Stream，保留原始 payload、失败原因、失败时间。
运维可通过该 Stream 回放或分析问题事件。
"""

from __future__ import annotations

from typing import Any

import orjson
from redis.asyncio import Redis

from fangyu_shared.logging import get_logger
from fangyu_shared.metrics import stream_dead_letter_total
from fangyu_shared.utils.time import utcnow_ms

_logger = get_logger("worker.dead_letter")


class DeadLetterHandler:
    def __init__(
        self,
        redis: Redis,
        *,
        stream_name: str = "fangyu:events:decision:dlq",
        maxlen: int = 100_000,
    ) -> None:
        self._redis = redis
        self._stream = stream_name
        self._maxlen = maxlen

    async def publish(
        self,
        *,
        message_id: str,
        payload: dict[str, Any],
        reason: str,
    ) -> None:
        try:
            await self._redis.xadd(
                name=self._stream,
                fields={
                    "message_id": message_id,
                    "payload": orjson.dumps(payload).decode(),
                    "reason": reason,
                    "failed_at_ms": str(utcnow_ms()),
                },
                maxlen=self._maxlen,
                approximate=True,
            )
            stream_dead_letter_total.labels(stream=self._stream, reason=reason[:64]).inc()
        except Exception as exc:
            _logger.error(
                "dead_letter_publish_failed",
                message_id=message_id,
                reason=reason,
                error=str(exc),
            )

    async def publish_many(
        self,
        items: list[tuple[str, dict[str, Any], str]],
    ) -> None:
        if not items:
            return
        pipeline = self._redis.pipeline(transaction=False)
        for message_id, payload, reason in items:
            pipeline.xadd(
                name=self._stream,
                fields={
                    "message_id": message_id,
                    "payload": orjson.dumps(payload).decode(),
                    "reason": reason,
                    "failed_at_ms": str(utcnow_ms()),
                },
                maxlen=self._maxlen,
                approximate=True,
            )
        try:
            await pipeline.execute()
            for _, _, reason in items:
                stream_dead_letter_total.labels(stream=self._stream, reason=reason[:64]).inc()
        except Exception as exc:
            _logger.error("dead_letter_pipeline_failed", error=str(exc), count=len(items))

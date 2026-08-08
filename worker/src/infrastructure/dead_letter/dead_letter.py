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
    ) -> set[str]:
        """批量转移到死信，返回**确实落盘**的 message_id 集合。

        必须返回落盘结果而不是静默吞掉异常：调用方要靠它决定哪些消息可以 ACK。
        「已转移到死信」意味着事件仍可被回放，「静默丢弃」则是数据永久消失——
        前者 ACK 是安全的，后者 ACK 等于自己删掉了唯一的补偿机会。
        """
        if not items:
            return set()
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
        # raise_on_error=False：整批里个别 XADD 失败不应掩盖其余成功的条目，
        # 否则会把「大部分已落盘」误判成「全部失败」而重复投递。
        try:
            replies = await pipeline.execute(raise_on_error=False)
        except Exception as exc:
            # 整条 pipeline 未能送达（连接断开等），没有任何条目落盘。
            _logger.error("dead_letter_pipeline_failed", error=str(exc), count=len(items))
            return set()

        persisted: set[str] = set()
        for (message_id, _payload, reason), reply in zip(items, replies, strict=False):
            if isinstance(reply, Exception):
                _logger.error(
                    "dead_letter_publish_failed",
                    message_id=message_id,
                    reason=reason,
                    error=str(reply),
                )
                continue
            persisted.add(message_id)
            stream_dead_letter_total.labels(stream=self._stream, reason=reason[:64]).inc()
        return persisted

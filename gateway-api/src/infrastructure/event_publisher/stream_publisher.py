"""决策事件发布器。

将决策事件写入 Redis Stream，供 worker 异步消费入库。
写入时附加 W3C traceparent 字段，实现跨进程 Trace 传播。
写入失败不阻塞主链路，通过日志与指标暴露。
"""

from __future__ import annotations

from typing import Any

import orjson
from redis.asyncio import Redis

from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.event import DecisionEvent
from fangyu_shared.tracing import get_traceparent

_logger = get_logger("gateway.event_publisher")


class StreamEventPublisher:
    """Redis Stream 事件发布器。"""

    def __init__(
        self,
        redis: Redis,
        *,
        stream_name: str = "fangyu:events:decision",
        maxlen: int = 500_000,
        approximate: bool = True,
    ) -> None:
        self._redis = redis
        self._stream = stream_name
        self._maxlen = maxlen
        self._approximate = approximate

    async def publish(self, event: DecisionEvent) -> str | None:
        payload: dict[str, Any] = {
            "payload": orjson.dumps(event.model_dump(by_alias=True, mode="json")).decode(),
        }
        traceparent = get_traceparent()
        if traceparent:
            payload["traceparent"] = traceparent
        try:
            result = await self._redis.xadd(
                name=self._stream,
                fields=payload,
                maxlen=self._maxlen,
                approximate=self._approximate,
            )
            return result if isinstance(result, str) else result.decode() if result else None
        except Exception as exc:
            _logger.error("stream_publish_failed", error=str(exc), event_id=event.event_id)
            return None

    async def publish_batch(self, events: list[DecisionEvent]) -> int:
        if not events:
            return 0
        pipeline = self._redis.pipeline(transaction=False)
        for event in events:
            payload = orjson.dumps(event.model_dump(by_alias=True, mode="json")).decode()
            pipeline.xadd(
                self._stream,
                {"payload": payload},
                maxlen=self._maxlen,
                approximate=self._approximate,
            )
        try:
            results = await pipeline.execute()
            return sum(1 for r in results if r)
        except Exception as exc:
            _logger.error("stream_publish_batch_failed", error=str(exc), count=len(events))
            return 0

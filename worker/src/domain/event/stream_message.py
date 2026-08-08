"""Stream 消息值对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fangyu_shared.schemas.event import DecisionEvent


@dataclass(frozen=True, slots=True)
class StreamMessage:
    """从 Redis Stream 读取到的原始消息。"""

    stream: str
    message_id: str
    payload: dict[str, Any]
    delivered_count: int = 1
    traceparent: str | None = field(default=None, compare=False)

    def as_event(self) -> DecisionEvent:
        return DecisionEvent.model_validate(self.payload)

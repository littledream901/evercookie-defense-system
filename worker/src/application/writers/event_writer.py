"""事件写入编排器：转换 + 批量写入 + DLQ。"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.logging import get_logger

from src.application.transformers.event_transformer import EventTransformer, TransformResult
from src.domain.event.stream_message import StreamMessage
from src.infrastructure.clickhouse_batch.batch_writer import BatchWriter, WriteResult
from src.infrastructure.dead_letter.dead_letter import DeadLetterHandler

_logger = get_logger("worker.event_writer")


@dataclass(slots=True)
class WriterOutcome:
    ack_ids: list[str]
    dead_letter_count: int


class EventWriter:
    def __init__(
        self,
        *,
        transformer: EventTransformer,
        batch_writer: BatchWriter,
        dead_letter: DeadLetterHandler,
    ) -> None:
        self._transformer = transformer
        self._batch_writer = batch_writer
        self._dead_letter = dead_letter

    async def handle(self, messages: list[StreamMessage]) -> WriterOutcome:
        if not messages:
            return WriterOutcome(ack_ids=[], dead_letter_count=0)

        transformed: TransformResult = self._transformer.transform(messages)
        ack_ids: list[str] = []
        dead_letter_items: list[tuple[str, dict, str]] = []

        for mid, payload, reason in transformed.invalid:
            dead_letter_items.append((mid, payload, reason))
            ack_ids.append(mid)  # 无效数据直接 ACK 以避免重复处理

        if transformed.rows:
            write_result: WriteResult = await self._batch_writer.write_batch(
                transformed.rows,
                message_ids=transformed.row_message_ids,
            )
            ack_ids.extend(write_result.succeeded_ids)
            # 写入失败的进入 DLQ
            payload_map = {m.message_id: m.payload for m in messages}
            for mid, reason in write_result.failed_ids:
                dead_letter_items.append((mid, payload_map.get(mid, {}), f"write_error:{reason[:200]}"))
                ack_ids.append(mid)

        if dead_letter_items:
            await self._dead_letter.publish_many(dead_letter_items)
            _logger.warning(
                "dead_letter_dispatched",
                count=len(dead_letter_items),
                batch_size=len(messages),
            )

        return WriterOutcome(ack_ids=ack_ids, dead_letter_count=len(dead_letter_items))

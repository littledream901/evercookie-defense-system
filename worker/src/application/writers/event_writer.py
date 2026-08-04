"""事件写入编排器：转换 + 批量写入 + DLQ。"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.logging import get_logger

from src.application.transformers.event_transformer import EventTransformer, TransformResult
from src.application.transformers.trace_transformer import TraceTransformer
from src.domain.event.stream_message import StreamMessage
from src.infrastructure.clickhouse_batch.batch_writer import BatchWriter, WriteResult
from src.infrastructure.dead_letter.dead_letter import DeadLetterHandler

_logger = get_logger("worker.event_writer")


@dataclass(slots=True)
class WriterOutcome:
    ack_ids: list[str]
    dead_letter_count: int
    trace_rows_written: int = 0
    """写入 ``decision_traces`` 的明细行数。仅用于观测，不参与 ACK 判定。"""


class EventWriter:
    def __init__(
        self,
        *,
        transformer: EventTransformer,
        batch_writer: BatchWriter,
        dead_letter: DeadLetterHandler,
        trace_transformer: TraceTransformer | None = None,
        trace_batch_writer: BatchWriter | None = None,
    ) -> None:
        self._transformer = transformer
        self._batch_writer = batch_writer
        self._dead_letter = dead_letter
        self._trace_transformer = trace_transformer
        self._trace_batch_writer = trace_batch_writer
        """明细写入器。两者任一为 None 即关闭明细落库（``decision_traces`` 保持空表）。"""

    async def handle(self, messages: list[StreamMessage]) -> WriterOutcome:
        if not messages:
            return WriterOutcome(ack_ids=[], dead_letter_count=0)

        transformed: TransformResult = self._transformer.transform(messages)
        ack_ids: list[str] = []
        dead_letter_items: list[tuple[str, dict, str]] = []

        # 无效数据不在这里 ACK：必须等确认落入 DLQ 之后才能 ACK，
        # 否则 DLQ 写失败时消息已被 ACK，事件就彻底消失了。
        for mid, payload, reason in transformed.invalid:
            dead_letter_items.append((mid, payload, reason))

        trace_rows = 0
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

            # 明细写在主表之后：主表是事实来源，明细只是排障辅助。
            # 只为成功入主表的消息写明细，避免主表失败重投后明细重复累积
            # （decision_traces 是 MergeTree，没有去重能力）。
            succeeded = set(write_result.succeeded_ids)
            trace_rows = await self._write_traces(
                [m for m in messages if m.message_id in succeeded]
            )

        dead_letter_count = 0
        if dead_letter_items:
            persisted = await self._dead_letter.publish_many(dead_letter_items)
            # 只 ACK 真正落入 DLQ 的消息。未落盘的保持 pending，
            # 后续由 claim_stale 抢回重试——留在 pending 里可以重来，
            # ACK 掉就再也找不回来了。
            ack_ids.extend(mid for mid, _payload, _reason in dead_letter_items if mid in persisted)
            dead_letter_count = len(persisted)
            failed_count = len(dead_letter_items) - dead_letter_count
            _logger.warning(
                "dead_letter_dispatched",
                count=dead_letter_count,
                not_persisted=failed_count,
                batch_size=len(messages),
            )
            if failed_count:
                # 这批消息既没写进 ClickHouse 也没写进 DLQ，只能靠 pending 重投。
                _logger.error(
                    "dead_letter_persist_failed_left_pending",
                    count=failed_count,
                )

        return WriterOutcome(
            ack_ids=ack_ids,
            dead_letter_count=dead_letter_count,
            trace_rows_written=trace_rows,
        )

    async def _write_traces(self, messages: list[StreamMessage]) -> int:
        """写规则条件命中明细，返回写入行数。

        整段 best-effort，不产出 DLQ 也不影响 ACK：明细缺失只让排障视图少一份
        参考数据，任何统计口径都不依赖它。反过来，若让明细写入失败阻塞 ACK，
        一张 TTL 只有 7 天的辅助表就能把主链路的消费进度卡死。

        ``decision_traces`` 是 MergeTree（无去重），因此重复写入会留下重复行。
        调用方只传「已成功入主表」的消息，把重复窗口收敛到「主表成功但明细写
        失败」这一种情况——此时明细整批丢弃，不重试。
        """
        if self._trace_transformer is None or self._trace_batch_writer is None:
            return 0
        if not messages:
            return 0
        try:
            rows = self._trace_transformer.transform(messages)
            if not rows:
                return 0
            # message_ids 传等长占位：明细是一对多，与消息不存在一一对应关系，
            # 这里不消费 BatchWriter 的成功/失败清单，只借它的批量+重试能力。
            result = await self._trace_batch_writer.write_batch(
                rows, message_ids=[""] * len(rows)
            )
            if result.failed_ids:
                _logger.warning(
                    "decision_trace_write_partial_failure",
                    failed=len(result.failed_ids),
                    total=len(rows),
                )
            return len(result.succeeded_ids)
        except Exception as exc:  # noqa: BLE001 - 明细失败不该阻塞主链路 ACK
            _logger.warning("decision_trace_write_failed", error=str(exc))
            return 0

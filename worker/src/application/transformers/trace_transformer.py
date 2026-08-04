"""条件明细转换器：Stream 消息 → ``decision_traces`` 行。

与 :mod:`event_transformer` 的分工
---------------------------------
一条 Stream 消息产出**一行**主表记录，但可能产出**多行**明细（一个请求评估了
多条规则、每条规则多个条件）。两者的基数不同，所以拆成两个转换器：主表转换
必须严格保证「消息 ↔ 行」一一对应（DLQ 与 ACK 都依赖这个关系），明细则是
一对多，且允许整批丢弃。

明细缺失只影响排障视图，不影响任何统计口径，因此这里不产出 DLQ 条目：
脏明细直接跳过，绝不能让它拖着主表事件一起进 DLQ。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.logging import get_logger

# 复用主表转换器的时间解析，保证同一事件在两张表里的 occurred_at 完全一致。
from src.application.transformers.event_transformer import _parse_datetime
from src.domain.event.stream_message import StreamMessage

_logger = get_logger("worker.trace_transformer")

# 与 ConditionTraceEvent / gateway 侧收集上限一致。
_MAX_TRACES_PER_EVENT = 200

_MAX_RULE_NAME = 128
_MAX_FIELD = 64
_MAX_OP = 24
_MAX_VALUE = 512


class TraceTransformer:
    """Stream 消息 → ``decision_traces`` 行。"""

    def transform(self, messages: list[StreamMessage]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for msg in messages:
            try:
                rows.extend(self._rows_for(msg.payload))
            except Exception as exc:  # noqa: BLE001 - 坏明细不该影响主表事件
                _logger.warning(
                    "trace_transform_failed",
                    message_id=msg.message_id,
                    error=str(exc),
                )
        return rows

    @classmethod
    def _rows_for(cls, raw: dict[str, Any]) -> list[dict[str, Any]]:
        traces = raw.get("conditionTraces") or raw.get("condition_traces") or []
        if not isinstance(traces, list) or not traces:
            return []

        # request_id 是这张表的点查键；缺了就无从检索，整批明细没有保存价值。
        request_id = str(raw.get("requestId") or raw.get("request_id") or "")
        if not request_id:
            return []
        app_id = _to_int(raw.get("appId") or raw.get("app_id"))
        if app_id <= 0:
            return []

        occurred_at = _parse_datetime(raw.get("occurredAt") or raw.get("occurred_at"))

        rows: list[dict[str, Any]] = []
        for item in traces[:_MAX_TRACES_PER_EVENT]:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "request_id": request_id,
                    "app_id": app_id,
                    "rule_id": _to_int(item.get("ruleId") or item.get("rule_id")),
                    "rule_name": str(item.get("ruleName") or item.get("rule_name") or "")[
                        :_MAX_RULE_NAME
                    ],
                    # ClickHouse 侧列名是 field，事件侧别名同为 field
                    # （Python 属性名 field_path，避开 dataclasses.field）。
                    "field": str(item.get("field") or item.get("field_path") or "")[:_MAX_FIELD],
                    "op": str(item.get("op") or "")[:_MAX_OP],
                    "expected": str(item.get("expected") or "")[:_MAX_VALUE],
                    "actual": str(item.get("actual") or "")[:_MAX_VALUE],
                    "matched": 1 if _to_bool(item.get("matched")) else 0,
                    "occurred_at": occurred_at,
                }
            )
        return rows


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}

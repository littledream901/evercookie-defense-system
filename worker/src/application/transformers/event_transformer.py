"""事件转换器：Stream 消息 → ClickHouse 行。

幂等设计：
- 每条事件必须携带 ``event_id``；缺失或空值 → 直接丢 DLQ 而非静默补默认值。
- ClickHouse 侧使用 ``ReplacingMergeTree(event_version)`` 去重，配合本转换器
  兜底填充的 ``event_version = occurred_at_ms`` 保证同一 event_id 的重复写入
  最终收敛到"发生时间戳最大"的那条。
- ``schema_version`` 由发布端携带，缺失时兜底为 :data:`fangyu_shared.schemas.event.DECISION_EVENT_SCHEMA_VERSION`。

字段命名兼容：
- Gateway 使用 camelCase（``eventId`` / ``appId`` / ``occurredAt``），
- 老数据可能使用 snake_case（``event_id`` / ``app_id`` / ``occurred_at``），
- 本转换器同时接受两种命名。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.event import DECISION_EVENT_SCHEMA_VERSION

from src.domain.event.stream_message import StreamMessage

_logger = get_logger("worker.event_transformer")

_DEFAULT_IP_TYPE = "ipv4"


@dataclass(slots=True)
class TransformResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_message_ids: list[str] = field(default_factory=list)
    invalid: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)


class EventTransformer:
    """Stream 消息 → ClickHouse 行。"""

    def transform(self, messages: list[StreamMessage]) -> TransformResult:
        result = TransformResult()
        for msg in messages:
            try:
                row = self._to_ch_row(msg.payload)
                if not row["event_id"]:
                    raise ValueError("missing event_id")
                if row["app_id"] <= 0:
                    raise ValueError("invalid app_id")
                result.rows.append(row)
                result.row_message_ids.append(msg.message_id)
            except Exception as exc:
                _logger.warning(
                    "event_transform_failed",
                    message_id=msg.message_id,
                    error=str(exc),
                )
                result.invalid.append((msg.message_id, msg.payload, f"transform_error:{exc}"))
        return result

    @classmethod
    def _to_ch_row(cls, raw: dict[str, Any]) -> dict[str, Any]:
        occurred_at_raw = raw.get("occurredAt") or raw.get("occurred_at")
        occurred_at = _parse_datetime(occurred_at_raw)
        occurred_ms = int(occurred_at.timestamp() * 1000)

        rule_ids_raw = raw.get("ruleIds") or raw.get("rule_ids") or []

        event_version = (
            _to_int(raw.get("eventVersion") or raw.get("event_version"))
            or occurred_ms
            or int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        )
        schema_version = (
            _to_int(raw.get("schemaVersion") or raw.get("schema_version"))
            or DECISION_EVENT_SCHEMA_VERSION
        )

        shadow_ids_raw = raw.get("shadowRuleIds") or raw.get("shadow_rule_ids") or []
        shadow_verdicts_raw = raw.get("shadowVerdicts") or raw.get("shadow_verdicts") or []
        scorer_scores_raw = raw.get("scorerScores") or raw.get("scorer_scores") or {}
        clock_counts_raw = raw.get("clockCounts") or raw.get("clock_counts") or {}

        return {
            "event_id": str(raw.get("eventId") or raw.get("event_id") or ""),
            "app_id": _to_int(raw.get("appId") or raw.get("app_id")) or 0,
            "fingerprint": str(raw.get("fingerprint") or ""),
            "device_id": str(raw.get("deviceId") or raw.get("device_id") or ""),
            "ip": str(raw.get("ip") or ""),
            "ip_type": str(raw.get("ipType") or raw.get("ip_type") or _DEFAULT_IP_TYPE),
            "user_agent": str(raw.get("userAgent") or raw.get("user_agent") or ""),
            "path": str(raw.get("path") or "/"),
            "referer": str(raw.get("referer") or ""),
            "method": str(raw.get("method") or "GET"),
            # 处置三层
            "verdict": str(raw.get("verdict") or "trusted"),
            "mechanism": str(raw.get("mechanism") or "pass"),
            "target_kind": str(raw.get("targetKind") or raw.get("target_kind") or "origin"),
            "target_url": str(raw.get("targetUrl") or raw.get("target_url") or ""),
            "http_status": _to_int(raw.get("httpStatus") or raw.get("http_status")) or 200,
            # 处置溯源
            "decided_by": str(raw.get("decidedBy") or raw.get("decided_by") or "system_default"),
            "decided_stage": str(raw.get("decidedStage") or raw.get("decided_stage") or "default"),
            "decided_rule_id": _to_int(raw.get("decidedRuleId") or raw.get("decided_rule_id")),
            # 评分
            "score": _to_float(raw.get("score")) or 0.0,
            "scorer_scores": _to_score_map(scorer_scores_raw),
            "rule_ids": [int(x) for x in rule_ids_raw if str(x).isdigit()],
            "reason": str(raw.get("reason") or ""),
            # 网络解析结果
            "country": str(raw.get("country") or ""),
            "asn": _to_int(raw.get("asn")),
            "connection_type": str(
                raw.get("connectionType") or raw.get("connection_type") or "unknown"
            ),
            # 设备解析结果
            "device_type": str(raw.get("deviceType") or raw.get("device_type") or ""),
            "os_name": str(raw.get("osName") or raw.get("os_name") or ""),
            "browser_name": str(raw.get("browserName") or raw.get("browser_name") or ""),
            "is_bot": 1 if _to_bool(raw.get("isBot") or raw.get("is_bot")) else 0,
            "crawler_category": str(
                raw.get("crawlerCategory") or raw.get("crawler_category") or ""
            ),
            "crawler_vendor": str(raw.get("crawlerVendor") or raw.get("crawler_vendor") or ""),
            # 客户端语言偏好
            "accept_language": str(raw.get("acceptLanguage") or raw.get("accept_language") or ""),
            # 访客追踪
            "repeat_key": str(raw.get("repeatKey") or raw.get("repeat_key") or ""),
            "repeat_value": str(raw.get("repeatValue") or raw.get("repeat_value") or ""),
            "evercookie_restore": (
                1 if _to_bool(raw.get("evercookieRestore") or raw.get("evercookie_restore")) else 0
            ),
            # 影子评估
            "shadow_rule_ids": [int(x) for x in shadow_ids_raw if str(x).isdigit()],
            "shadow_verdicts": [str(x) for x in shadow_verdicts_raw],
            # 接入来源
            "ingress": str(raw.get("ingress") or "sdk"),
            "fingerprint_is_derived": (
                1
                if _to_bool(
                    raw.get("fingerprintIsDerived") or raw.get("fingerprint_is_derived")
                )
                else 0
            ),
            # Clock
            "clock_counts": _to_count_map(clock_counts_raw),
            "clock_banned": 1 if _to_bool(raw.get("clockBanned") or raw.get("clock_banned")) else 0,
            "behavior_event_count": _to_int(
                raw.get("behaviorEventCount") or raw.get("behavior_event_count")
            ),
            # 性能
            "decision_cost_ms": _to_int(
                raw.get("decisionCostMs") or raw.get("decision_cost_ms")
            ),
            "request_id": str(raw.get("requestId") or raw.get("request_id") or ""),
            "occurred_at": occurred_at,
            "schema_version": schema_version,
            "event_version": event_version,
        }


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _to_score_map(value: Any) -> dict[str, float]:
    """归一化 scorer 分数为 ClickHouse Map(String, Float32)。

    脏数据逐条跳过：单个 scorer 名/分值异常不应导致整条事件进 DLQ。
    """
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw in value.items():
        name = str(key)[:32]
        if not name:
            continue
        try:
            out[name] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def _to_count_map(value: Any) -> dict[str, int]:
    """归一化 Clock 计数为 ClickHouse Map(String, UInt32)。

    负值截为 0：UInt32 不接受负数，写入会直接报错拖垮整批。
    """
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key, raw in value.items():
        name = str(key)[:32]
        if not name:
            continue
        try:
            out[name] = max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return out


def _parse_datetime(value: Any) -> datetime:
    if value is None or value == "":
        return datetime.now(tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        # 秒 vs 毫秒 vs 微秒
        ts = int(value)
        if ts >= 10**14:
            ts //= 1000
        elif ts < 10**11:
            ts *= 1000
        return datetime.utcfromtimestamp(ts / 1000.0)
    text = str(value)
    try:
        # ISO 8601 → UTC naive
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return datetime.now(tz=timezone.utc).replace(tzinfo=None)

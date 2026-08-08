"""事件转换器：Stream 消息 → ClickHouse 行。

幂等设计：
- 每条事件必须携带 ``event_id``；缺失或空值 → 直接丢 DLQ 而非静默补默认值。
- ClickHouse 侧使用 ``ReplacingMergeTree(event_version)`` 去重，配合本转换器
  兜底填充的 ``event_version = occurred_at_ms`` 保证同一 event_id 的重复写入
  最终收敛到"发生时间戳最大"的那条。
- ``schema_version`` 由发布端携带，缺失时兜底为 :data:`fangyu_shared.schemas.event.DECISION_EVENT_SCHEMA_VERSION`。

字段命名兼容：
- Gateway 使用 camelCase（``eventId`` / ``siteId`` / ``occurredAt``），
- 老数据可能使用 snake_case（``event_id`` / ``site_id`` / ``occurred_at``），
- V3 之前的站点标识键名为 ``appId`` / ``app_id``，滚动发布期间 Stream 里两种
  键名会并存，因此保留旧键名兜底读取。
- 本转换器同时接受上述命名。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.decision import IngressKind
from fangyu_shared.schemas.disposition import Mechanism, TargetKind, Verdict
from fangyu_shared.schemas.event import DECISION_EVENT_SCHEMA_VERSION

from src.domain.event.stream_message import StreamMessage

_logger = get_logger("worker.event_transformer")

_DEFAULT_IP_TYPE = "ipv4"

# 脏值哨兵。不用空串是为了让「上游发了没见过的值」和「上游没发」在看板上可区分。
_UNKNOWN = "unknown"

# LowCardinality 列白名单。任意字符串直写会污染字典，且所有按这些列
# GROUP BY 的物化视图都会长出无意义的分组，事后无法从数据里剔除。
_VERDICT_VALUES = frozenset(v.value for v in Verdict)
_MECHANISM_VALUES = frozenset(m.value for m in Mechanism)
_TARGET_KIND_VALUES = frozenset(t.value for t in TargetKind)
_INGRESS_VALUES = frozenset(i.value for i in IngressKind)

# decided_by 的事实来源是 gateway 的 src.domain.decision.disposition.DecidedBy，
# 它属于 gateway 服务内部模块、worker 无法 import，因此在此镜像一份。
# 改动 gateway 侧枚举时必须同步这里，否则新来源会被记成 unknown。
_DECIDED_BY_VALUES = frozenset(
    {
        "whitelist",
        "challenge_pass",
        "clock_ban",
        "clock_rate_limit",
        "hybrid_layer",
        "decision_rule",
        "group_no_match",
        "threat_intel",
        "security",
        "scoring",
        "app_default",
        "system_default",
    }
)

# 自由文本列长度上限。截断而非拒绝：这些字段只用于排障与展示，
# 不参与判定，为超长 UA 丢掉整条事件会连带丢失它的裁决与评分。
_MAX_USER_AGENT = 512
_MAX_HOST = 256
_MAX_PATH = 2048
_MAX_REFERER = 2048
_MAX_TARGET_URL = 2048


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
                if row["site_id"] <= 0:
                    raise ValueError("invalid site_id")
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
            # V3 改名为 siteId；appId / app_id 是旧键名兜底：
            # 滚动发布期间 Stream 里会同时存在两种键名的在途消息，
            # 直接切换会让旧消息因 site_id=0 全部进 DLQ。
            "site_id": _to_int(
                raw.get("siteId")
                or raw.get("site_id")
                or raw.get("appId")
                or raw.get("app_id")
            )
            or 0,
            "fingerprint": str(raw.get("fingerprint") or ""),
            "device_id": str(raw.get("deviceId") or raw.get("device_id") or ""),
            "ip": str(raw.get("ip") or ""),
            "ip_type": str(raw.get("ipType") or raw.get("ip_type") or _DEFAULT_IP_TYPE),
            "user_agent": str(raw.get("userAgent") or raw.get("user_agent") or "")[
                :_MAX_USER_AGENT
            ],
            "host": str(raw.get("host") or "")[:_MAX_HOST],
            "path": str(raw.get("path") or "/")[:_MAX_PATH],
            "referer": str(raw.get("referer") or "")[:_MAX_REFERER],
            "method": str(raw.get("method") or "GET"),
            # 处置三层
            "verdict": _enum_or_unknown(
                raw.get("verdict") or "trusted", _VERDICT_VALUES, column="verdict"
            ),
            "mechanism": _enum_or_unknown(
                raw.get("mechanism") or "pass", _MECHANISM_VALUES, column="mechanism"
            ),
            "target_kind": _enum_or_unknown(
                raw.get("targetKind") or raw.get("target_kind") or "origin",
                _TARGET_KIND_VALUES,
                column="target_kind",
            ),
            "target_url": str(raw.get("targetUrl") or raw.get("target_url") or "")[
                :_MAX_TARGET_URL
            ],
            "http_status": _to_int(raw.get("httpStatus") or raw.get("http_status")) or 200,
            # 处置溯源
            "decided_by": _enum_or_unknown(
                raw.get("decidedBy") or raw.get("decided_by") or "system_default",
                _DECIDED_BY_VALUES,
                column="decided_by",
            ),
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
            "asn_org": str(raw.get("asnOrg") or raw.get("asn_org") or "")[:256],
            "connection_type": str(
                raw.get("connectionType") or raw.get("connection_type") or "unknown"
            ),
            "is_vpn": 1 if _to_bool(raw.get("isVpn") or raw.get("is_vpn")) else 0,
            "is_proxy": 1 if _to_bool(raw.get("isProxy") or raw.get("is_proxy")) else 0,
            # 设备解析结果
            "device_type": str(raw.get("deviceType") or raw.get("device_type") or ""),
            "os_name": str(raw.get("osName") or raw.get("os_name") or ""),
            "browser_name": str(raw.get("browserName") or raw.get("browser_name") or ""),
            "is_bot": 1 if _to_bool(raw.get("isBot") or raw.get("is_bot")) else 0,
            "crawler_name": str(raw.get("crawlerName") or raw.get("crawler_name") or ""),
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
            "ingress": _enum_or_unknown(
                raw.get("ingress") or "sdk", _INGRESS_VALUES, column="ingress"
            ),
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


def _enum_or_unknown(value: Any, allowed: frozenset[str], *, column: str) -> str:
    """枚举列取值校验：不在白名单内则降级为哨兵值。

    与 :func:`_to_score_map` 保持同一取舍——脏的那一个字段降级，整条事件仍然入库。
    枚举列多是次要维度（如 decided_by），为它丢掉整条事件会连带丢失
    event_id / score / 裁决这些无可替代的信息，代价远大于一个维度失真。
    降级同时打 warning，脏值本身记在日志里供上游排查。
    """
    text = str(value)
    if text in allowed:
        return text
    _logger.warning("event_enum_value_rejected", column=column, value=text[:64])
    return _UNKNOWN


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

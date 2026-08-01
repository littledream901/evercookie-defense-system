"""事件标准化统一入口.

支持从 admin-api / worker 两端接入的原始事件字段，统一转成 NormalizedEvent。
"""

from __future__ import annotations

from typing import Any

from .constants import (
    DISPATCH_LABELS,
    DISPATCH_TYPE_MAP,
    IP_TYPE_ALIASES,
    IP_TYPE_LABELS,
)
from .types import NormalizedEvent


class EventNormalizer:
    """无状态的事件标准化工具类."""

    # ------------------ 字段级 normalize ------------------

    @staticmethod
    def normalize_timestamp_ms(value: Any) -> int | None:
        """时间戳统一转成毫秒级 int.

        规则：
            - None / 空字符串 → None
            - 秒（长度 <= 10）→ ×1000
            - 微秒（长度 >= 16）→ ÷1000
            - 毫秒（默认）→ 原样返回
            - 非法输入 → None（不抛异常）
        """
        if value is None or value == "":
            return None
        try:
            ts = int(float(value))
        except (TypeError, ValueError):
            return None
        if ts < 0:
            return None
        if ts < 10**11:  # 秒
            return ts * 1000
        if ts >= 10**14:  # 微秒
            return ts // 1000
        return ts

    @staticmethod
    def normalize_dispatch_type(value: Any) -> str:
        """分流类型标准化为字符串.

        支持输入：整数 1/2/3、已标准化字符串。
        """
        if isinstance(value, bool):
            return "unknown"
        if isinstance(value, int):
            return DISPATCH_TYPE_MAP.get(value, "unknown")
        if isinstance(value, str):
            key = value.strip().lower()
            if key in {"1", "2", "3"}:
                return DISPATCH_TYPE_MAP.get(int(key), "unknown")
            if key in DISPATCH_TYPE_MAP.values():
                return key
        return "unknown"

    @staticmethod
    def dispatch_label(dispatch_type: str | int) -> str:
        """根据分流类型返回中文标签."""
        return DISPATCH_LABELS.get(dispatch_type, "未知")

    @staticmethod
    def normalize_ip_type(value: Any) -> str:
        """IP 类型标准化为大写枚举字符串."""
        if value is None:
            return "UNKNOWN"
        raw = str(value).strip()
        # 别名转换
        alias = IP_TYPE_ALIASES.get(raw.lower())
        if alias:
            return alias
        upper = raw.upper()
        if upper in IP_TYPE_LABELS:
            return upper
        return "UNKNOWN"

    @staticmethod
    def ip_type_label(ip_type: str) -> str:
        """IP 类型标签."""
        return IP_TYPE_LABELS.get(ip_type, "未知")

    @staticmethod
    def normalize_string(value: Any, max_length: int = 2048) -> str | None:
        """字符串字段标准化：去空白、限制长度、非空返回."""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text[:max_length]

    @staticmethod
    def normalize_int(value: Any) -> int | None:
        """整数字段标准化."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def normalize_bool(value: Any) -> bool:
        """布尔字段标准化."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "t"}
        return False

    # ------------------ 事件级 normalize ------------------

    @classmethod
    def normalize(cls, entry: dict[str, Any]) -> NormalizedEvent:
        """将原始事件字典标准化为 NormalizedEvent."""
        if not isinstance(entry, dict):
            entry = {}

        dispatch_type = cls.normalize_dispatch_type(entry.get("dispatch_type"))
        ip_type = cls.normalize_ip_type(entry.get("ip_type"))

        return NormalizedEvent(
            timestamp=cls.normalize_timestamp_ms(entry.get("timestamp")),
            request_id=cls.normalize_string(entry.get("request_id"), max_length=128),
            site_id=cls.normalize_string(entry.get("site_id"), max_length=64),
            app_id=cls.normalize_string(entry.get("app_id"), max_length=64),
            device_id=cls.normalize_string(entry.get("device_id"), max_length=128),
            dispatch_type=dispatch_type,
            dispatch_label=cls.dispatch_label(dispatch_type),
            ip=cls.normalize_string(entry.get("ip"), max_length=64),
            ip_type=ip_type,
            ip_type_label=cls.ip_type_label(ip_type),
            country=cls.normalize_string(entry.get("country"), max_length=8),
            asn=cls.normalize_int(entry.get("asn")),
            user_agent=cls.normalize_string(entry.get("user_agent") or entry.get("ua")),
            referer=cls.normalize_string(entry.get("referer")),
            url=cls.normalize_string(entry.get("url")),
            language=cls.normalize_string(entry.get("language"), max_length=32),
            risk_score=cls.normalize_int(entry.get("risk_score")),
            matched_rule_id=cls.normalize_string(entry.get("matched_rule_id"), max_length=64),
            matched_rule_name=cls.normalize_string(entry.get("matched_rule_name"), max_length=128),
            cached=cls.normalize_bool(entry.get("cached")),
            latency_ms=cls.normalize_int(entry.get("latency_ms")),
            extra=entry.get("extra") if isinstance(entry.get("extra"), dict) else {},
        )

    @classmethod
    def normalize_batch(cls, entries: list[dict[str, Any]]) -> list[NormalizedEvent]:
        """批量标准化."""
        return [cls.normalize(e) for e in entries or []]

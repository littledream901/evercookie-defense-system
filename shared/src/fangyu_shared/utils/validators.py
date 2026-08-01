"""输入校验工具。"""

from __future__ import annotations

import ipaddress
import re

_FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")


def is_valid_app_id(value: object) -> bool:
    return isinstance(value, int) and value > 0


def is_valid_fingerprint(value: object) -> bool:
    return isinstance(value, str) and bool(_FINGERPRINT_RE.fullmatch(value))


def ensure_positive_int(value: object, field: str = "value") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} 必须为正整数")
    return value


def ensure_ip(value: str, field: str = "ip") -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ValueError(f"{field} 不是合法 IP: {value!r}") from exc

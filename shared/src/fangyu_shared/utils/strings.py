"""字符串处理工具，包含日志脱敏。"""

from __future__ import annotations

import ipaddress


def truncate(value: str | None, max_length: int = 128, suffix: str = "...") -> str:
    if not value:
        return ""
    if len(value) <= max_length:
        return value
    return value[: max_length - len(suffix)] + suffix


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def mask_ip(ip: str | None) -> str:
    """IP 脱敏：IPv4 保留前两段，IPv6 保留前四段。"""
    if not ip:
        return ""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return "***"
    if isinstance(parsed, ipaddress.IPv4Address):
        parts = ip.split(".")
        return ".".join(parts[:2] + ["*", "*"])
    parts = ip.split(":")
    keep = parts[:4]
    return ":".join(keep + ["*"] * max(0, len(parts) - 4))

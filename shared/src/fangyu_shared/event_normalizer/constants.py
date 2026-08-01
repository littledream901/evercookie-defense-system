"""事件标准化常量表."""

from __future__ import annotations

from typing import Final

# 分流类型：数字 / 字符串 → 标签
DISPATCH_LABELS: Final[dict[str | int, str]] = {
    1: "目标页",
    2: "安全页",
    3: "拦截页",
    "money_page": "目标页",
    "safe_page": "安全页",
    "high_risk": "拦截页",
    "unknown": "未知",
}

# 数字 → 字符串标准化
DISPATCH_TYPE_MAP: Final[dict[int, str]] = {
    1: "money_page",
    2: "safe_page",
    3: "high_risk",
}

# IP 类型标签
IP_TYPE_LABELS: Final[dict[str, str]] = {
    "RESIDENTIAL": "住宅",
    "DATACENTER": "数据中心",
    "MOBILE": "移动网络",
    "TOR": "Tor 网络",
    "PROXY": "代理",
    "VPN": "VPN",
    "HOSTING": "主机托管",
    "EDUCATION": "教育网",
    "GOVERNMENT": "政府",
    "COMMERCIAL": "商业",
    "UNKNOWN": "未知",
}

# 归一化前置转换（大小写、别名）
IP_TYPE_ALIASES: Final[dict[str, str]] = {
    "residential": "RESIDENTIAL",
    "datacenter": "DATACENTER",
    "data_center": "DATACENTER",
    "dc": "DATACENTER",
    "mobile": "MOBILE",
    "tor": "TOR",
    "proxy": "PROXY",
    "vpn": "VPN",
    "hosting": "HOSTING",
    "unknown": "UNKNOWN",
    "": "UNKNOWN",
}

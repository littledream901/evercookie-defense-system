"""情报 Redis key 约定。

admin-api 负责写入（全量同步），gateway-api 只读。两侧必须引用同一常量，
避免此前 ``fangyu:threat_intel`` 那样在两处各自硬编码字符串。
"""

from __future__ import annotations

_PREFIX = "fangyu:intel"

ASN_KEY = f"{_PREFIX}:asn"
"""Hash：asn(str) → JSON(network_type/country/risk_score/operator)。"""

CRAWLER_KEY = f"{_PREFIX}:crawler"
"""Hash：pattern → JSON(category/name/is_legitimate/risk_score)。"""

FINGERPRINT_KEY = f"{_PREFIX}:fingerprint"
"""Hash：finger_id → JSON(finger_type/risk_score)。"""

GEO_IP_KEY = f"{_PREFIX}:geo_ip"
"""Hash：cidr → JSON(country/region/city)。"""

IP_PROFILE_KEY = f"{_PREFIX}:ip_profile"
"""Hash：cidr → JSON(network_type/is_vpn/is_proxy/is_tor/risk_score)。"""

SYNC_TIME_KEY = f"{_PREFIX}:last_sync"
"""String：最近一次全量同步的 ISO 时间戳，供 overview 展示。"""

_KEY_MAP = {
    "asn": ASN_KEY,
    "crawler": CRAWLER_KEY,
    "fingerprint": FINGERPRINT_KEY,
    "geo_ip": GEO_IP_KEY,
    "ip_profile": IP_PROFILE_KEY,
}


def intel_key(intel_type: str) -> str:
    """按情报类型取 Redis key。"""
    try:
        return _KEY_MAP[intel_type]
    except KeyError as exc:
        raise ValueError(f"未知情报类型：{intel_type}") from exc

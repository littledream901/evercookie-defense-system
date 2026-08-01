"""Gateway 侧威胁情报 Redis 查询器。

只做读操作，零数据库连接，纯 Redis SISMEMBER O(1)。
"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.redis_manager import RedisManager

_PREFIX = "fangyu:threat_intel"
_ALL_KEY = f"{_PREFIX}:all"


@dataclass(frozen=True, slots=True)
class ThreatIntelResult:
    is_threat: bool
    categories: list[str]


class ThreatIntelReader:
    """从 Redis 查询 IP 是否在威胁情报库中。"""

    _KNOWN_CATEGORIES = ["malicious", "proxy", "vpn", "tor", "datacenter", "bot"]

    @classmethod
    def _key(cls, category: str) -> str:
        return f"{_PREFIX}:{category}"

    @classmethod
    async def check(cls, ip: str) -> ThreatIntelResult:
        redis = RedisManager.get_client()
        if not await redis.sismember(_ALL_KEY, ip):
            return ThreatIntelResult(is_threat=False, categories=[])
        matched: list[str] = []
        for cat in cls._KNOWN_CATEGORIES:
            if await redis.sismember(cls._key(cat), ip):
                matched.append(cat)
        return ThreatIntelResult(is_threat=True, categories=matched)

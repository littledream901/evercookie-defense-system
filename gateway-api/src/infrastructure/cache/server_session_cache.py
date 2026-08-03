"""服务端会话缓存（Hybrid 双层架构专用）。

CF Worker / Nginx-Lua 第一层做出 pass 决策时，把预判结果存入此缓存，
key = serverToken（sst_<hex32>）。

SDK 发起第二次 /v2/decide 时携带同一 token，decision_service 可在 HYBRID_LOOKUP
阶段取出第一层的信号，将其注入 context.extra 供后续评分阶段引用。

TTL 设为 5 分钟——绝大多数用户在首页加载后 5 分钟内完成 SDK 初始化。
超过 TTL 未被消费的 entry 自动过期，不会占用无效内存。

数据结构（存储）：
    {
        "verdict":   "trusted" | "suspect" | "hostile",
        "score":     float,         # 第一层评分（0-100）
        "reason":    str | null,
        "ip":        str,           # 第一层看到的访客 IP（冗余存储，供日志）
        "userAgent": str,
        "ingress":   "adapter",
    }
"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

_KEY_PREFIX = "fy:sst"
_DEFAULT_TTL = 300  # 5 分钟


class ServerSessionEntry:
    """轻量数据类；不用 Pydantic 以保持序列化成本极低。"""

    __slots__ = ("verdict", "mechanism", "decided_by", "score", "reason", "ip", "user_agent")

    def __init__(
        self,
        verdict: str,
        score: float,
        reason: str | None,
        ip: str,
        user_agent: str,
        mechanism: str = "pass",
        decided_by: str = "scoring",
    ) -> None:
        self.verdict = verdict
        self.mechanism = mechanism
        self.decided_by = decided_by
        self.score = score
        self.reason = reason
        self.ip = ip
        self.user_agent = user_agent

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "mechanism": self.mechanism,
            "decidedBy": self.decided_by,
            "score": self.score,
            "reason": self.reason,
            "ip": self.ip,
            "userAgent": self.user_agent,
            "ingress": "adapter",
        }

    @classmethod
    def from_dict(cls, d: dict) -> ServerSessionEntry:
        return cls(
            verdict=d.get("verdict", "unknown"),
            mechanism=d.get("mechanism", "pass"),
            decided_by=d.get("decidedBy", "scoring"),
            score=float(d.get("score", 0.0)),
            reason=d.get("reason"),
            ip=d.get("ip", ""),
            user_agent=d.get("userAgent", ""),
        )


class ServerSessionCache:
    """存取服务端会话预判。"""

    def __init__(self, redis: Redis, *, ttl: int = _DEFAULT_TTL) -> None:
        self._redis = redis
        self._ttl = ttl

    @staticmethod
    def _key(token: str) -> str:
        return f"{_KEY_PREFIX}:{token}"

    async def set(self, token: str, entry: ServerSessionEntry) -> None:
        await self._redis.set(
            self._key(token),
            orjson.dumps(entry.to_dict()),
            ex=self._ttl,
        )

    async def get(self, token: str) -> ServerSessionEntry | None:
        raw = await self._redis.get(self._key(token))
        if raw is None:
            return None
        try:
            return ServerSessionEntry.from_dict(orjson.loads(raw))
        except (orjson.JSONDecodeError, KeyError, TypeError):
            return None

    async def delete(self, token: str) -> None:
        """消费后删除，防止重放。"""
        await self._redis.delete(self._key(token))

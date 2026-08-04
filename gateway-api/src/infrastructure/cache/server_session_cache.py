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
from fangyu_shared.logging import get_logger
from redis.asyncio import Redis

_logger = get_logger("gateway.server_session_cache")

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
        """写入第一层预判。

        Redis 故障按**写入失败**静默处理（fail-open）：写不进去的后果是 SDK
        二次请求的 HYBRID_LOOKUP 查不到，退化成只用第二层指纹判断——这正是
        未启用 Hybrid 时的行为，不是安全缺口。反之让异常冒泡就是 adapter 侧
        每个请求都 500，代价严重得多。
        """
        try:
            await self._redis.set(
                self._key(token),
                orjson.dumps(entry.to_dict()),
                ex=self._ttl,
            )
        except Exception as exc:
            _logger.warning("server_session_set_failed", error=str(exc))

    async def get(self, token: str) -> ServerSessionEntry | None:
        """读取第一层预判。故障与未命中同样处理：继续走完整流水线。"""
        try:
            raw = await self._redis.get(self._key(token))
        except Exception as exc:
            _logger.warning("server_session_get_failed", error=str(exc))
            return None
        if raw is None:
            return None
        try:
            return ServerSessionEntry.from_dict(orjson.loads(raw))
        except (orjson.JSONDecodeError, KeyError, TypeError):
            return None

    async def delete(self, token: str) -> None:
        """消费后删除，防止重放。

        删除失败只静默记日志：token 本身有 5 分钟 TTL 兜底，重放窗口上限就是
        这个 TTL，而且重放拿到的是同一条第一层结论、不能提权。为了收紧这个
        窄窗口而让决策返回 500 是明显划不来的交换。
        """
        try:
            await self._redis.delete(self._key(token))
        except Exception as exc:
            _logger.warning("server_session_delete_failed", error=str(exc))

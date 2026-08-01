"""决策结果缓存。

命中缓存可直接跳过后续流水线，是热点路径的关键优化。
Key 设计：fangyu:decide:v2:{app_id}:{fingerprint}:{ip_hash}

为什么缓存 CachedDecision 而不是 DecisionResponse
-------------------------------------------------
缓存 key **不含 URL**。若把已渲染 ``target_url`` 的完整响应写进缓存，同一
访客访问不同页面时会复用第一次的渲染结果，跳转地址串味。因此缓存只存
未渲染的处置（占位符原样保留），渲染在每次响应构造时重做。
"""

from __future__ import annotations

import orjson
from pydantic import Field
from redis.asyncio import Redis

from fangyu_shared.schemas.common import BaseSchema
from fangyu_shared.schemas.disposition import Disposition
from fangyu_shared.utils.crypto import sha256_hex

_KEY_PREFIX = "fangyu:decide:v2"


class CachedDecision(BaseSchema):
    """可缓存的决策核心：不含任何按请求渲染的字段。"""

    disposition: Disposition
    score: float = 0.0
    rule_ids: list[int] = Field(default_factory=list, alias="ruleIds")
    reason: str | None = None
    decided_by: str = Field(default="default", alias="decidedBy")
    decided_stage: str = Field(default="default", alias="decidedStage")

    @property
    def ttl_seconds(self) -> int:
        return self.disposition.ttl_seconds


class DecisionCache:
    """决策缓存。"""

    def __init__(self, redis: Redis, *, default_ttl: int = 60) -> None:
        self._redis = redis
        self._default_ttl = default_ttl

    @staticmethod
    def make_key(app_id: int, fingerprint: str, ip: str) -> str:
        ip_hash = sha256_hex(ip)[:12]
        return f"{_KEY_PREFIX}:{app_id}:{fingerprint}:{ip_hash}"

    async def get(self, app_id: int, fingerprint: str, ip: str) -> CachedDecision | None:
        key = self.make_key(app_id, fingerprint, ip)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return CachedDecision.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValueError):
            await self._redis.delete(key)
            return None

    async def set(
        self,
        app_id: int,
        fingerprint: str,
        ip: str,
        decision: CachedDecision,
        *,
        ttl: int | None = None,
    ) -> None:
        key = self.make_key(app_id, fingerprint, ip)
        payload = orjson.dumps(decision.model_dump(by_alias=True, mode="json"))
        await self._redis.set(key, payload, ex=ttl or decision.ttl_seconds or self._default_ttl)

    async def invalidate(self, app_id: int, fingerprint: str, ip: str) -> None:
        await self._redis.delete(self.make_key(app_id, fingerprint, ip))

"""决策结果缓存。

命中缓存可直接跳过后续流水线，是热点路径的关键优化。
Key 设计：fangyu:decide:v2:{site_id}:{fingerprint}:{ip_hash}

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

from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.common import BaseSchema
from fangyu_shared.schemas.disposition import Disposition, Mechanism, Verdict
from fangyu_shared.utils.crypto import sha256_hex

_logger = get_logger("gateway.decision_cache")

_KEY_PREFIX = "fangyu:decide:v2"


class CachedShadowHit(BaseSchema):
    """随决策一起缓存的影子命中记录。

    只存 ``verdict``/``mechanism`` 而不存完整 ``Disposition``：影子数据的唯一
    消费方是「影响面测算」（事件里的 shadow_rule_ids / shadow_verdicts 与响应
    里的 ShadowOutcome），两者都只读这两个字段。存完整 Disposition 会把
    target.url_pool（最多 32 个地址）也带进缓存条目，让每条缓存膨胀数倍，
    而多出来的字节没有任何消费方。
    """

    rule_id: int | None = Field(default=None, alias="ruleId")
    rule_name: str = Field(default="", alias="ruleName")
    verdict: Verdict
    mechanism: Mechanism


class CachedDecision(BaseSchema):
    """可缓存的决策核心：不含任何按请求渲染的字段。"""

    disposition: Disposition
    score: float = 0.0
    rule_ids: list[int] = Field(default_factory=list, alias="ruleIds")
    reason: str | None = None
    decided_by: str = Field(default="default", alias="decidedBy")
    decided_stage: str = Field(default="default", alias="decidedStage")
    shadow_hits: list[CachedShadowHit] = Field(default_factory=list, alias="shadowHits")
    """原次完整评估产出的影子命中。

    缓存它是为了让缓存命中的流量也能贡献影响面数据——稳态下缓存命中占多数，
    不缓存影子结果等于影响面测算只看得到冷启动流量，测出来的比例系统性偏小。
    默认空列表保证旧版缓存条目（无此字段）仍能反序列化。
    """

    @property
    def ttl_seconds(self) -> int:
        return self.disposition.ttl_seconds


class DecisionCache:
    """决策缓存。"""

    def __init__(self, redis: Redis, *, default_ttl: int = 60) -> None:
        self._redis = redis
        self._default_ttl = default_ttl

    @staticmethod
    def make_key(site_id: int, fingerprint: str, ip: str) -> str:
        ip_hash = sha256_hex(ip)[:12]
        return f"{_KEY_PREFIX}:{site_id}:{fingerprint}:{ip_hash}"

    async def get(self, site_id: int, fingerprint: str, ip: str) -> CachedDecision | None:
        key = self.make_key(site_id, fingerprint, ip)
        # 捕获全部异常：缓存查不到只是少了一次加速，回落到完整流水线即可；
        # 让 Redis 故障冒泡会把 /v2/decide 直接变成 500——这是本服务里唯一
        # 「性能优化组件把可用性拖下来」的形态。收窄成 RedisError 会漏掉连接池
        # 耗尽等被包装过的异常。
        try:
            raw = await self._redis.get(key)
        except Exception as exc:
            _logger.warning("decision_cache_get_failed", site_id=site_id, error=str(exc))
            return None
        if raw is None:
            return None
        try:
            return CachedDecision.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValueError):
            # 脏数据顺手删掉，避免每次请求都反序列化失败。删除本身失败无所谓：
            # 这条 key 到期自然消失，为它把决策变成 500 不值得。
            try:
                await self._redis.delete(key)
            except Exception as exc:
                _logger.warning("decision_cache_evict_failed", site_id=site_id, error=str(exc))
            return None

    async def set(
        self,
        site_id: int,
        fingerprint: str,
        ip: str,
        decision: CachedDecision,
        *,
        ttl: int | None = None,
    ) -> None:
        key = self.make_key(site_id, fingerprint, ip)
        payload = orjson.dumps(decision.model_dump(by_alias=True, mode="json"))
        # 写失败只损失下一次的加速机会，结论本身已经算出来并即将下发。
        try:
            await self._redis.set(key, payload, ex=ttl or decision.ttl_seconds or self._default_ttl)
        except Exception as exc:
            _logger.warning("decision_cache_set_failed", site_id=site_id, error=str(exc))

    async def invalidate(self, site_id: int, fingerprint: str, ip: str) -> None:
        # 失效走的是管理面（规则发布等），不在决策热路径上，因此仍向调用方
        # 暴露异常——这里静默失败会让「改了规则却没生效」变成无迹可查的问题。
        await self._redis.delete(self.make_key(site_id, fingerprint, ip))

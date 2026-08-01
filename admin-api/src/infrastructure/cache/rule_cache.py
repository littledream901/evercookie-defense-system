"""规则缓存写入：admin 发布规则后同步到 Redis 供 gateway 读取。"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

from fangyu_shared.schemas.rule import DecisionRule, ScoringRule

AnyRule = DecisionRule | ScoringRule

_KEY_PREFIX = "fangyu:rules"


class RuleCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def sync_app_rules(self, app_id: int, rules: list[AnyRule]) -> None:
        key = f"{_KEY_PREFIX}:{app_id}"
        pipe = self._redis.pipeline()
        pipe.delete(key)
        if rules:
            mapping = {
                str(rule.id): orjson.dumps(rule.model_dump(by_alias=True, mode="json"))
                for rule in rules
                if rule.id is not None
            }
            if mapping:
                pipe.hset(key, mapping=mapping)
        await pipe.execute()

    async def upsert(self, rule: AnyRule) -> None:
        if rule.id is None:
            return
        key = f"{_KEY_PREFIX}:{rule.app_id}"
        payload = orjson.dumps(rule.model_dump(by_alias=True, mode="json"))
        await self._redis.hset(key, str(rule.id), payload)

    async def remove(self, app_id: int, rule_id: int) -> None:
        await self._redis.hdel(f"{_KEY_PREFIX}:{app_id}", str(rule_id))

"""规则仓储：本地 LRU + Redis 缓存双层结构。

- 一级：进程内 LRU（TTL 30s）
- 二级：Redis Hash（由 admin-api 主动写入 / 定期刷新）
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import orjson
from redis.asyncio import Redis

from fangyu_shared.schemas.rule import DecisionRule, RuleGroup, RuleSet, ScoringRule

_REDIS_PREFIX = "fangyu:rules"
_GROUP_PREFIX = "fangyu:rule_groups"


@dataclass(slots=True)
class _CacheEntry:
    rule_set: RuleSet
    expires_at: float


@dataclass(slots=True)
class RuleRepositoryConfig:
    local_ttl_seconds: float = 30.0
    max_local_entries: int = 512


class RuleRepository:
    """规则仓储。"""

    def __init__(
        self,
        redis: Redis,
        *,
        config: RuleRepositoryConfig | None = None,
    ) -> None:
        self._redis = redis
        self._config = config or RuleRepositoryConfig()
        self._local: dict[int, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get_rule_set(self, app_id: int) -> RuleSet:
        entry = self._local.get(app_id)
        now = time.time()
        if entry and entry.expires_at > now:
            return entry.rule_set

        async with self._lock:
            entry = self._local.get(app_id)
            if entry and entry.expires_at > now:
                return entry.rule_set
            rule_set = await self._load_from_redis(app_id)
            self._local[app_id] = _CacheEntry(
                rule_set=rule_set,
                expires_at=now + self._config.local_ttl_seconds,
            )
            self._trim_local()
            return rule_set

    async def _load_from_redis(self, app_id: int) -> RuleSet:
        raw_items: dict[str, Any] = await self._redis.hgetall(f"{_REDIS_PREFIX}:{app_id}")
        decision_rules: list[DecisionRule] = []
        scoring_rules: list[ScoringRule] = []
        for raw in raw_items.values():
            try:
                data = orjson.loads(raw)
            except orjson.JSONDecodeError:
                continue
            # 按 kind 分派；脏数据逐条跳过，不影响其余规则加载
            kind = str(data.get("kind") or "decision")
            try:
                if kind == "scoring":
                    scoring_rules.append(ScoringRule.model_validate(data))
                else:
                    decision_rules.append(DecisionRule.model_validate(data))
            except ValueError:
                continue

        groups: list[RuleGroup] = []
        raw_groups: dict[str, Any] = await self._redis.hgetall(f"{_GROUP_PREFIX}:{app_id}")
        for raw in raw_groups.values():
            try:
                groups.append(RuleGroup.model_validate(orjson.loads(raw)))
            except (orjson.JSONDecodeError, ValueError):
                continue

        return RuleSet(
            appId=app_id,
            decisionRules=decision_rules,
            scoringRules=scoring_rules,
            groups=groups,
        )

    async def invalidate(self, app_id: int) -> None:
        self._local.pop(app_id, None)

    def _trim_local(self) -> None:
        if len(self._local) <= self._config.max_local_entries:
            return
        overflow = len(self._local) - self._config.max_local_entries
        # 按到期时间由早至晚删除
        keys = sorted(self._local.keys(), key=lambda k: self._local[k].expires_at)[:overflow]
        for k in keys:
            self._local.pop(k, None)

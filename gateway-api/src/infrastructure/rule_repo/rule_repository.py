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

# admin 侧 RuleCache 换页时随快照写入的代次字段，不是规则，解析时必须跳过，
# 否则每次加载都会对它 model_validate 失败、刷一条无意义的脏数据日志。
# 规则 id 都是数字串，这个双下划线名字不会与任何 field 相撞。
_VERSION_FIELD = "__version__"


@dataclass(slots=True)
class _CacheEntry:
    rule_set: RuleSet
    expires_at: float
    version: str | None = None


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
            rule_set, version = await self._load_from_redis(app_id)
            self._local[app_id] = _CacheEntry(
                rule_set=rule_set,
                expires_at=now + self._config.local_ttl_seconds,
                version=version,
            )
            self._trim_local()
            return rule_set

    async def snapshot_version(self, app_id: int) -> str | None:
        """当前本地生效的快照代次，用于观测「gateway 是否已看到最新快照」。

        走 ``get_rule_set`` 同一条缓存，不额外打 Redis，因此也不改变 30s TTL 行为。
        """
        await self.get_rule_set(app_id)
        entry = self._local.get(app_id)
        return entry.version if entry else None

    async def _load_from_redis(self, app_id: int) -> tuple[RuleSet, str | None]:
        raw_items: dict[str, Any] = await self._redis.hgetall(f"{_REDIS_PREFIX}:{app_id}")
        decision_rules: list[DecisionRule] = []
        scoring_rules: list[ScoringRule] = []
        version: str | None = None
        for field, raw in raw_items.items():
            # 连接可能未开 decode_responses，field 统一归一化成 str 再比对
            name = field.decode() if isinstance(field, bytes) else str(field)
            if name == _VERSION_FIELD:
                version = raw.decode() if isinstance(raw, bytes) else str(raw)
                continue
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

        rule_set = RuleSet(
            appId=app_id,
            decisionRules=decision_rules,
            scoringRules=scoring_rules,
            groups=groups,
        )
        return rule_set, version

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

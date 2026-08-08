"""规则组缓存同步（admin → Redis，供 gateway 读取）。

规则组按站点分片存储在 ``fangyu:rule_groups:{site_id}`` Hash 中，
每个规则组的 field 为组 id，value 为 RuleGroup JSON。

Gateway 在加载规则集时读取对应站点的规则组，与决策规则一起构成完整的 RuleSet。
"""

from __future__ import annotations

from typing import Protocol

from fangyu_shared.schemas.rule import RuleGroup

_GROUP_PREFIX = "fangyu:rule_groups"


def _key(site_id: int) -> str:
    return f"{_GROUP_PREFIX}:{site_id}"


def _staging_key(site_id: int) -> str:
    """staging 临时键名，用于原子换页。"""
    return f"{_key(site_id)}:staging"


class _RedisLike(Protocol):
    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int: ...
    async def hdel(self, name: str, *keys: str) -> int: ...
    async def delete(self, *names: str) -> int: ...
    async def rename(self, src: str, dst: str) -> bool: ...


class RuleGroupCache:
    """把已启用的规则组写入 Redis，供 gateway 按站点读取。"""

    def __init__(self, redis: _RedisLike) -> None:
        self._redis = redis

    async def replace_site(self, site_id: int, groups: list[RuleGroup]) -> None:
        """全量重写某站点的规则组分片（原子换页）。
        
        使用 staging + RENAME 实现无空窗期更新：
        1. 先写入 staging key
        2. RENAME staging → live（单条原子命令）
        3. Gateway 的 HGETALL 要么读到完整旧快照、要么读到完整新快照
        
        Args:
            site_id: 站点 ID
            groups: 规则组列表（只包含 enabled=True 的组）
        """
        live = _key(site_id)
        staging = _staging_key(site_id)
        
        mapping: dict[str, str] = {}
        for group in groups:
            if not group.enabled:
                continue
            mapping[str(group.id)] = group.model_dump_json(by_alias=True)
        
        if not mapping:
            # 空规则组：站点可能合法地禁用了所有规则组，必须删除线上 key
            # RENAME 要求源 key 存在，空 Hash 在 Redis 中等于不存在，所以直接删除
            await self._redis.delete(live, staging)
            return
        
        # 清理可能残留的 staging key，写入新数据，原子换页
        await self._redis.delete(staging)
        await self._redis.hset(staging, mapping=mapping)
        await self._redis.rename(staging, live)

    async def upsert_one(self, group: RuleGroup) -> None:
        """写入或更新单个规则组。"""
        if not group.enabled:
            # 禁用的组应该从缓存移除
            await self.remove_one(group.site_id, group.id)  # type: ignore[arg-type]
            return
        
        await self._redis.hset(
            _key(group.site_id),
            str(group.id),
            group.model_dump_json(by_alias=True),
        )

    async def remove_one(self, site_id: int, group_id: int) -> None:
        """从缓存中移除单个规则组。"""
        await self._redis.hdel(_key(site_id), str(group_id))

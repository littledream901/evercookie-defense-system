"""规则缓存同步（admin → Redis，供 gateway 读取）。

规则与站点是多对多关系：一条规则可绑定多个站点。Redis 仍按站点分片存储
（``fangyu:rules:{site_id}``），因此同一条规则会被写入其所有绑定站点的分片，
每份的 ``appId`` 字段置为该分片对应的 site_id，gateway 侧读取逻辑无需改动。
"""

from __future__ import annotations

from typing import Protocol

from fangyu_shared.schemas.rule import DecisionRule, RuleStatus, ScoringRule

AnyRule = DecisionRule | ScoringRule

_KEY_PREFIX = "fangyu:rules:"


def _key(site_id: int) -> str:
    return f"{_KEY_PREFIX}{site_id}"


class _RedisLike(Protocol):
    async def hset(self, name: str, key: str, value: str) -> int: ...
    async def hdel(self, name: str, *keys: str) -> int: ...
    async def delete(self, *names: str) -> int: ...


class RuleCache:
    """把已发布规则写入 Redis，供 gateway 按站点读取。"""

    def __init__(self, redis: _RedisLike) -> None:
        self._redis = redis

    async def replace_site(self, site_id: int, rules: list[AnyRule]) -> None:
        """全量重写某站点的规则分片。

        先 delete 再逐条 hset，确保已解绑/已下线的规则不会残留在分片里。
        """
        await self._redis.delete(_key(site_id))
        for rule in rules:
            if rule.status != RuleStatus.PUBLISHED:
                continue
            await self._write_one(site_id, rule)

    async def upsert_to_sites(self, rule: AnyRule, site_ids: list[int]) -> None:
        """把一条规则写入指定站点的所有分片。"""
        for site_id in site_ids:
            await self._write_one(site_id, rule)

    async def remove_from_sites(self, rule_id: int, site_ids: list[int]) -> None:
        """从指定站点的分片中移除一条规则。"""
        for site_id in site_ids:
            await self._redis.hdel(_key(site_id), str(rule_id))

    async def _write_one(self, site_id: int, rule: AnyRule) -> None:
        # appId 按目标分片改写：gateway 读到的每条规则都自带正确的站点归属
        payload = rule.model_copy(update={"app_id": site_id})
        await self._redis.hset(
            _key(site_id),
            str(rule.id),
            payload.model_dump_json(by_alias=True),
        )

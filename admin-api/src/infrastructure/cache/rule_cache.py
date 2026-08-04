"""规则缓存同步（admin → Redis，供 gateway 读取）。

规则与站点是多对多关系：一条规则可绑定多个站点。Redis 仍按站点分片存储
（``fangyu:rules:{site_id}``），因此同一条规则会被写入其所有绑定站点的分片，
每份的 ``appId`` 字段置为该分片对应的 site_id，gateway 侧读取逻辑无需改动。

全量重写走 staging key + RENAME 原子换页（见 ``replace_site``）：gateway 的
HGETALL 只会看到旧快照或新快照，不会看到中间的空/半量状态。这一点对风控系统
是硬要求——读到空规则集等于「没有规则命中」，会直接放行，属于错误的失败方向。
"""

from __future__ import annotations

from typing import Protocol

from fangyu_shared.schemas.rule import DecisionRule, ScoringRule
from fangyu_shared.utils.time import utcnow_ms

from src.domain.rule.state_machine import SYNCABLE_STATUSES

AnyRule = DecisionRule | ScoringRule

_KEY_PREFIX = "fangyu:rules:"

# 快照代次字段，与规则同存一个 Hash，从而随 RENAME 一起原子换页。
# 规则 id 是数字串（``str(rule.id)``），双下划线包裹的名字不可能与之相撞，
# 所以能安全地占用同一命名空间，无需再开一个 key 去存版本（两个 key 就无法
# 保证「版本与数据同时可见」了）。
_VERSION_FIELD = "__version__"


def _key(site_id: int) -> str:
    return f"{_KEY_PREFIX}{site_id}"


def _staging_key(site_id: int) -> str:
    return f"{_key(site_id)}:staging"


class _RedisLike(Protocol):
    # 与 redis-py 的签名对齐：单条走 key/value，整份快照走 mapping 一次写入
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


class RuleCache:
    """把已发布与影子规则写入 Redis，供 gateway 按站点读取。"""

    def __init__(self, redis: _RedisLike) -> None:
        self._redis = redis

    async def replace_site(self, site_id: int, rules: list[AnyRule]) -> None:
        """全量重写某站点的规则分片（原子换页）。

        先把整份新快照写进 staging key，再 RENAME 覆盖线上 key。RENAME 是单条
        原子命令，gateway 的 HGETALL 要么读到完整旧快照、要么读到完整新快照。
        原实现是「delete 再逐条 hset」，两者之间存在一个空/半量窗口，gateway 把
        空规则集当作「无规则命中」放行，等于每次例行同步都短暂关闭了拦截。
        """
        live = _key(site_id)
        staging = _staging_key(site_id)

        mapping: dict[str, str] = {}
        for rule in rules:
            if rule.status not in SYNCABLE_STATUSES:
                continue
            mapping[str(rule.id)] = self._payload(site_id, rule)

        if not mapping:
            # 空快照不能直接 return：站点可能是合法地把所有规则都下线/解绑了，
            # 这个意图必须生效，否则线上 key 会一直留着已作废的旧规则。
            # 而 RENAME 在源 key 不存在时报错（空 Hash 在 Redis 里等于不存在），
            # 所以这一支只能显式删除线上 key。顺手清掉可能残留的 staging。
            await self._redis.delete(live, staging)
            return

        # 代次值随快照一起写入，gateway 读到的 version 与规则内容必然同源
        mapping[_VERSION_FIELD] = str(utcnow_ms())

        # 上一次换页若在中途失败，staging 可能有残留脏 field，先清干净
        await self._redis.delete(staging)
        await self._redis.hset(staging, mapping=mapping)
        await self._redis.rename(staging, live)

    async def upsert_to_sites(self, rule: AnyRule, site_ids: list[int]) -> None:
        """把一条规则写入指定站点的所有分片。"""
        for site_id in site_ids:
            await self._write_one(site_id, rule)

    async def remove_from_sites(self, rule_id: int, site_ids: list[int]) -> None:
        """从指定站点的分片中移除一条规则。"""
        for site_id in site_ids:
            await self._redis.hdel(_key(site_id), str(rule_id))

    async def _write_one(self, site_id: int, rule: AnyRule) -> None:
        await self._redis.hset(
            _key(site_id),
            str(rule.id),
            self._payload(site_id, rule),
        )

    @staticmethod
    def _payload(site_id: int, rule: AnyRule) -> str:
        # appId 按目标分片改写：gateway 读到的每条规则都自带正确的站点归属
        return rule.model_copy(update={"app_id": site_id}).model_dump_json(by_alias=True)

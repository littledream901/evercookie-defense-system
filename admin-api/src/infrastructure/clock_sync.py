"""把频控阈值与封禁写入 Redis，供 gateway 读取。

键格式与序列化形状**必须**与 gateway 侧读取严格一致，否则会静默失效：
``get_limits`` 解析失败只记 warning 然后回退默认值，站点收紧的阈值不生效，
而且日志里看不出是 admin 写错了格式。所以这里一律复用
:mod:`fangyu_shared.clock.windows` 的键构造函数，不手写字符串拼接。

V1 的教训：admin 侧写 ``clock:ban:{ip}``，gateway 侧读
``fangyu:clock:ban:{app_id}:{dim}:{value}``——前缀不同且缺 app_id 维度，
封禁写了但网关永远读不到。
"""

from __future__ import annotations

import orjson
from fangyu_shared.clock.windows import ClockDimension, ban_key, limits_key
from fangyu_shared.schemas.clock import ClockLimits
from redis.asyncio import Redis


class ClockSync:
    """Clock 配置的 Redis 写入面。

    走实例注入而非静态类，与 ``RuleCache`` 一致——便于测试传入替身，也避免
    隐式依赖进程级单例。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def put_limits(self, limits: ClockLimits) -> None:
        """写入站点阈值。

        用 ``by_alias=True`` 序列化成 camelCase：gateway 侧走
        ``ClockLimits.model_validate``，虽然 ``populate_by_name`` 让两种命名都能
        解析，但落库形状与 wire 契约保持一致可以避免后续改动踩坑。

        **刻意不设 TTL**。阈值是配置不是缓存，过期后无人重建会导致防护静默
        放宽——这与 threat_intel 的 24h TTL 策略不同，那边有定时全量重建兜底。
        """
        payload = orjson.dumps(limits.model_dump(by_alias=True))
        await self._redis.set(limits_key(limits.app_id), payload)

    async def delete_limits(self, app_id: int) -> None:
        """删除站点阈值，gateway 随即回退到默认值。"""
        await self._redis.delete(limits_key(app_id))

    async def ban(
        self,
        app_id: int,
        dimension: ClockDimension,
        value: str,
        *,
        seconds: int,
        reason: str,
    ) -> None:
        """写入封禁。TTL 即剩余时长，与 gateway 侧 ``ClockRepository.ban`` 同形。"""
        if seconds <= 0:
            return
        payload = orjson.dumps({"reason": reason, "dimension": dimension.value})
        await self._redis.set(
            ban_key(app_id, dimension, value), payload, ex=seconds
        )

    async def unban(self, app_id: int, dimension: ClockDimension, value: str) -> bool:
        """解封。返回是否确实删掉了一条（用于区分 404）。"""
        removed = await self._redis.delete(ban_key(app_id, dimension, value))
        return bool(removed)

    async def get_ban(
        self, app_id: int, dimension: ClockDimension, value: str
    ) -> dict | None:
        """查询封禁状态与剩余时长。"""
        key = ban_key(app_id, dimension, value)
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.get(key)
            pipe.ttl(key)
            raw, ttl = await pipe.execute()
        if not raw:
            return None
        try:
            meta = orjson.loads(raw)
        except orjson.JSONDecodeError:
            meta = {}
        return {
            "dimension": dimension.value,
            "value": value,
            "reason": meta.get("reason", ""),
            "ttlSeconds": max(0, int(ttl or 0)),
        }

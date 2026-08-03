"""轮询地址池的 Redis 计数器（ROUND_ROBIN 策略用）。"""

from __future__ import annotations

from redis.asyncio import Redis


class RotationCounter:
    """轮转计数器，为地址池分配单调递增的下标。

    Redis key 设计
    --------------
    ``fangyu:rotation_counter:{app_id}:{rule_id}``

    每条规则一个独立计数器。用 INCR 原子递增，取模由 pick_by_index 完成。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, app_id: int, rule_id: int) -> str:
        return f"fangyu:rotation_counter:{app_id}:{rule_id}"

    async def next(self, app_id: int, rule_id: int) -> int:
        """获取下一个下标。"""
        key = self._key(app_id, rule_id)
        return await self._redis.incr(key)

    async def reset(self, app_id: int, rule_id: int) -> None:
        """重置计数器（规则修改地址池时调用）。"""
        key = self._key(app_id, rule_id)
        await self._redis.delete(key)

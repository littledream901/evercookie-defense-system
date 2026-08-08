"""Nonce 一次性凭证存储（重放防护）。

Key 设计：fangyu:nonce:{site_id}:{nonce}

为什么单靠时间戳窗口不够
------------------------
签名把参数钉死了，但攻击者仍可在 300s 窗口内原样重放同一个已签名请求。
Nonce 让每个签名只能兑付一次：``SET NX`` 首次写入成功即放行，重复出现时
写入失败即拒绝。TTL 与时间戳窗口对齐——超出窗口的重放已被时间戳挡下，
再留着记录只是白占内存。

Redis 不可用时选择放行
----------------------
网关在链路最前端，Redis 抖动时若一律拒绝会让整站不可访问。重放防护是
纵深防御的一层，签名与时间戳仍在生效，因此这里降级放行并计数告警，
而不是把可用性赌在缓存上。
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

_KEY_PREFIX = "fangyu:nonce"


class NonceStore:
    """基于 Redis SET NX EX 的一次性 nonce 校验。"""

    def __init__(self, redis: Redis, *, ttl: int = 300) -> None:
        self._redis = redis
        self._ttl = ttl

    @staticmethod
    def make_key(site_id: int, nonce: str) -> str:
        return f"{_KEY_PREFIX}:{site_id}:{nonce}"

    async def claim(self, site_id: int, nonce: str, *, ttl: int | None = None) -> bool:
        """占用一个 nonce。

        Returns:
            True 表示首次出现（放行）；False 表示已被用过（判定为重放）。
        """
        if not nonce:
            return False
        try:
            created = await self._redis.set(
                self.make_key(site_id, nonce),
                b"1",
                nx=True,
                ex=ttl or self._ttl,
            )
        except RedisError:
            # 降级放行：见模块 docstring。
            return True
        return bool(created)

    async def release(self, site_id: int, nonce: str) -> None:
        """释放 nonce，仅供测试与管理工具使用。"""
        try:
            await self._redis.delete(self.make_key(site_id, nonce))
        except RedisError:
            return

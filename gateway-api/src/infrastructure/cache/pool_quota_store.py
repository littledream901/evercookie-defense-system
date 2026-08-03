"""地址池配额存储（Redis 计数器 + TTL）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis


class PoolQuotaStore:
    """地址池配额计数器，用于限制单个地址的每日/每小时访问量。

    Redis key 设计
    --------------
    ``fangyu:pool_quota:{app_id}:{url_hash}:{period}``

    period 格式
    -----------
    - 每日配额：``d20260803``（UTC 日期）
    - 每小时配额：``h2026080314``（UTC 小时）

    用 UTC 而非本地时区：多地域部署时避免不同副本对"今日"理解不一致。

    TTL 策略
    --------
    首次 INCR 时设置 EXPIRE，对齐到自然日/自然小时的下一个边界，让 Redis
    自动清理过期计数器，避免无限累积。

    URL 哈希
    --------
    同 PoolHealthStore，用 blake2b(16) 避免 URL 长度导致 key 膨胀。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _url_hash(self, url: str) -> str:
        return hashlib.blake2b(url.encode("utf-8"), digest_size=16).hexdigest()

    def _period_key(self, granularity: str) -> tuple[str, int]:
        """生成时间周期 key 与 TTL（秒）。

        返回 (period_str, ttl_seconds)。
        period_str 用于 key，ttl_seconds 是到周期结束的剩余秒数。
        """
        now = datetime.now(tz=timezone.utc)
        if granularity == "daily":
            period = now.strftime("d%Y%m%d")
            # 用 timedelta 跨边界，避免手工 day+1 在月末/年末越界
            boundary = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        elif granularity == "hourly":
            period = now.strftime("h%Y%m%d%H")
            boundary = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            msg = f"Unknown granularity: {granularity}"
            raise ValueError(msg)
        # +60 宽限：TTL 略长于周期边界，防止时钟微小漂移导致计数器早于边界消失
        ttl = int((boundary - now).total_seconds()) + 60
        return period, ttl

    def _key(self, app_id: int, url: str, granularity: str) -> str:
        period, _ = self._period_key(granularity)
        return f"fangyu:pool_quota:{app_id}:{self._url_hash(url)}:{period}"

    async def consume(self, app_id: int, url: str, quota: int, granularity: str) -> bool:
        """消费一次配额。返回 True 表示在限额内，False 表示已超限。

        首次写入时设置 TTL，后续 INCR 不重置（避免永不过期）。
        """
        if quota <= 0:
            return True  # 配额 ≤ 0 视为不限

        key = self._key(app_id, url, granularity)
        _, ttl = self._period_key(granularity)

        current = await self._redis.incr(key)
        # 只在首次写入时设置 TTL——每次都设会让计数器永不过期
        if current == 1:
            await self._redis.expire(key, ttl)

        return current <= quota

    async def is_exhausted(self, app_id: int, url: str, quota: int, granularity: str) -> bool:
        """检查配额是否已耗尽（不消费）。"""
        if quota <= 0:
            return False  # 无限额永远不耗尽

        key = self._key(app_id, url, granularity)
        val = await self._redis.get(key)
        if val is None:
            return False  # 未使用过
        try:
            current = int(val)
        except (ValueError, TypeError):
            return False
        return current >= quota

    async def get_usage(self, app_id: int, url: str, granularity: str) -> int:
        """查询当前用量。"""
        key = self._key(app_id, url, granularity)
        val = await self._redis.get(key)
        if val is None:
            return 0
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    async def reset(self, app_id: int, url: str, granularity: str) -> None:
        """重置配额（手动清零）。"""
        key = self._key(app_id, url, granularity)
        await self._redis.delete(key)

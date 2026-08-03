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

from typing import Any

import orjson
from fangyu_shared.clock.windows import (
    ClockDimension,
    ban_key,
    ban_scan_pattern,
    limits_key,
    parse_ban_key,
)
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

    async def scan_bans(
        self,
        app_id: int,
        *,
        dimension: ClockDimension | None = None,
        cursor: int = 0,
        count: int = 200,
    ) -> tuple[int, list[dict[str, Any]]]:
        """游标扫描某 app 的封禁键，返回 ``(下一游标, 条目)``。

        用 ``SCAN`` 而不是 ``KEYS``：封禁键数量随攻击流量增长，可能到十万级，
        ``KEYS`` 会阻塞整个 Redis——网关的频控读写全都排在后面，等于把一次
        运维查询变成一次全站故障。

        游标透传给调用方而非在内部循环到底：一次请求扫完全库会让接口超时，
        也失去了「先看前几页就够了」的常见用法。注意 ``SCAN`` 的返回条数只是
        近似值，调用方不能用「返回条数不足」判断结束，只能看游标是否回到 0。

        逐条 ``TTL`` 会带来 N 次往返，因此对本批键用 pipeline 一次取回。
        """
        pattern = ban_scan_pattern(app_id, dimension)
        next_cursor, keys = await self._redis.scan(
            cursor=cursor, match=pattern, count=count
        )
        if not keys:
            return int(next_cursor), []

        text_keys = [_text(k) for k in keys]
        async with self._redis.pipeline(transaction=False) as pipe:
            for key in text_keys:
                pipe.get(key)
                pipe.ttl(key)
            flat = await pipe.execute()

        entries: list[dict[str, Any]] = []
        for idx, key in enumerate(text_keys):
            raw = flat[idx * 2]
            ttl = flat[idx * 2 + 1]
            if raw is None:
                # 扫描与取值之间封禁到期了。跳过而非报错——这是正常竞态，
                # 报错只会让列表接口在攻击高峰期随机失败。
                continue
            parsed = parse_ban_key(key)
            if parsed is None:
                continue
            _, dim, value = parsed
            try:
                meta = orjson.loads(raw)
            except (orjson.JSONDecodeError, TypeError, ValueError):
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            entries.append(
                {
                    "dimension": dim.value,
                    "value": value,
                    "reason": str(meta.get("reason", "")),
                    "ttlSeconds": max(0, int(ttl or 0)),
                }
            )
        entries.sort(key=lambda e: (e["dimension"], e["value"]))
        return int(next_cursor), entries

    async def unban_many(
        self, app_id: int, items: list[tuple[ClockDimension, str]]
    ) -> int:
        """批量解封，返回实际删除条数。

        误封通常成批发生（一个 NAT 出口下的整片设备、一次误配阈值），逐条调
        接口在这种场景下不实用。
        """
        if not items:
            return 0
        keys = [ban_key(app_id, dim, value) for dim, value in items]
        removed = await self._redis.delete(*keys)
        return int(removed or 0)


def _text(key: object) -> str:
    """SCAN 返回的键可能是 bytes（未开 decode_responses）或 str。"""
    if isinstance(key, bytes):
        return key.decode("utf-8", errors="replace")
    return str(key)

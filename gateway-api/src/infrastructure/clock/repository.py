"""Clock 存储：频控计数、封禁状态、行为时序。

单次往返完成读写
----------------
频控的关键约束是**每个请求都要走**，所以延迟预算极紧。这里把「记录本次访问 +
裁剪过期数据 + 各窗口计数 + 查封禁」全部塞进一个 pipeline，一次 RTT 完成。

与旧版的差异
------------
旧版为 1s/60s/1h 各建一套键，其中 ``clock:1h:*`` 还在同一个 key 上混用了 ZSet
与 Hash——``zadd`` 先把 key 建成 ZSet，随后 ``hincrby`` 必然 ``WRONGTYPE``，而
整批操作被 try/except 兜住，失败完全静默，导致 ``first_access_ts`` 恒为 0。
本实现只用 ZSet，多窗口靠 ``ZCOUNT`` 从同一份数据算出。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import orjson
from fangyu_shared.clock.behavior import make_member, normalize_event_time
from fangyu_shared.clock.windows import (
    ALL_WINDOWS,
    BEHAVIOR_MAX_SEQUENCE,
    BEHAVIOR_RETENTION_SECONDS,
    RETENTION_SECONDS,
    ClockDimension,
    ban_key,
    behavior_key,
    limits_key,
    rate_key,
)
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.clock import BehaviorEvent, ClockLimits, default_limits
from redis.asyncio import Redis

_logger = get_logger("gateway.clock")


@dataclass(frozen=True, slots=True)
class BanState:
    """封禁状态。"""

    banned: bool
    reason: str = ""
    ttl_seconds: int = 0


@dataclass(frozen=True, slots=True)
class DimensionCounts:
    """单个维度在各窗口的计数。

    ``counts`` 的键是窗口名（burst/short/hour），与 :class:`ClockLimits`
    的阈值键一致，判定时可直接对位比较。
    """

    dimension: ClockDimension
    value: str
    counts: dict[str, int]
    ban: BanState

    def count_for(self, window_name: str) -> int:
        return self.counts.get(window_name, 0)


@dataclass(frozen=True, slots=True)
class ClockReading:
    """一次 Clock 观测：两个维度的计数与封禁状态。"""

    ip: DimensionCounts
    fingerprint: DimensionCounts
    now_ms: int

    @property
    def active_ban(self) -> tuple[ClockDimension, BanState] | None:
        """任一维度处于封禁则返回该维度。IP 优先——影响面更大。"""
        if self.ip.ban.banned:
            return (ClockDimension.IP, self.ip.ban)
        if self.fingerprint.ban.banned:
            return (ClockDimension.FINGERPRINT, self.fingerprint.ban)
        return None


class ClockRepository:
    """Clock 的 Redis 存储层。"""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def touch_and_read(
        self,
        app_id: int,
        *,
        ip_hash: str,
        fingerprint: str,
        now_ms: int,
    ) -> ClockReading:
        """记录本次访问并读回两个维度的计数与封禁状态。

        写入与读取在同一 pipeline 内，本次访问**计入**返回的计数——判定时用
        ``>`` 比较，即「第 N+1 次才算超限」。
        """
        now_sec = now_ms / 1000.0
        cutoff = now_sec - RETENTION_SECONDS
        dims = (
            (ClockDimension.IP, ip_hash),
            (ClockDimension.FINGERPRINT, fingerprint),
        )

        # 整段都在 try 内：pipeline() 本身也可能抛（连接池耗尽等），
        # 只包 execute() 会让故障从这里逃出去，破坏 fail-open 保证。
        try:
            pipe = self._redis.pipeline()
            for dimension, value in dims:
                key = rate_key(app_id, dimension, value)
                # member 必须全局唯一：同一毫秒内的并发请求应各计一次。旧版用
                # 「毫秒取模」当序号，同毫秒的两次访问 member 相同而被 ZSet 静默
                # 去重，直接导致突发流量少计。这里用 uuid 片段保证唯一。
                pipe.zadd(key, {f"{now_ms}:{uuid.uuid4().hex[:12]}": now_sec})
                pipe.zremrangebyscore(key, "-inf", cutoff)
                for window in ALL_WINDOWS:
                    pipe.zcount(key, now_sec - window.seconds, now_sec)
                pipe.expire(key, RETENTION_SECONDS)
                pipe.get(ban_key(app_id, dimension, value))
                pipe.ttl(ban_key(app_id, dimension, value))
            results = await pipe.execute()
            return self._parse(dims, results, now_ms)
        except Exception as exc:
            # 频控不可用时放行而非拦截：Redis 故障不应升级为全站不可访问。
            _logger.error("clock_touch_failed", error=str(exc), app_id=app_id)
            return self._empty_reading(ip_hash, fingerprint, now_ms)

    @staticmethod
    def _ops_per_dimension() -> int:
        # zadd + zremrangebyscore + N*zcount + expire + get(ban) + ttl(ban)
        return 5 + len(ALL_WINDOWS)

    def _parse(
        self,
        dims: tuple[tuple[ClockDimension, str], ...],
        results: list,
        now_ms: int,
    ) -> ClockReading:
        """按固定步长解析 pipeline 结果。

        步长由 :meth:`_ops_per_dimension` 单点定义，新增窗口时不需要改解析逻辑
        （旧版用手工游标推进，加窗口就得同步改两处）。
        """
        stride = self._ops_per_dimension()
        parsed: dict[ClockDimension, DimensionCounts] = {}

        for idx, (dimension, value) in enumerate(dims):
            base = idx * stride
            counts = {
                window.name: int(results[base + 2 + w_idx] or 0)
                for w_idx, window in enumerate(ALL_WINDOWS)
            }
            ban_raw = results[base + 3 + len(ALL_WINDOWS)]
            ban_ttl = results[base + 4 + len(ALL_WINDOWS)]
            parsed[dimension] = DimensionCounts(
                dimension=dimension,
                value=value,
                counts=counts,
                ban=self._parse_ban(ban_raw, ban_ttl),
            )

        return ClockReading(
            ip=parsed[ClockDimension.IP],
            fingerprint=parsed[ClockDimension.FINGERPRINT],
            now_ms=now_ms,
        )

    @staticmethod
    def _parse_ban(raw: object, ttl: object) -> BanState:
        if not raw:
            return BanState(banned=False)
        reason = ""
        try:
            payload = orjson.loads(raw)  # type: ignore[arg-type]
            reason = str(payload.get("reason", ""))
        except (orjson.JSONDecodeError, TypeError, ValueError, AttributeError):
            reason = str(raw)
        ttl_int = int(ttl) if isinstance(ttl, int) and ttl > 0 else 0
        return BanState(banned=True, reason=reason, ttl_seconds=ttl_int)

    @staticmethod
    def _empty_reading(ip_hash: str, fingerprint: str, now_ms: int) -> ClockReading:
        """Redis 不可用时的空观测：全零计数、无封禁，等价于放行。"""
        empty_ban = BanState(banned=False)
        return ClockReading(
            ip=DimensionCounts(ClockDimension.IP, ip_hash, {}, empty_ban),
            fingerprint=DimensionCounts(
                ClockDimension.FINGERPRINT, fingerprint, {}, empty_ban
            ),
            now_ms=now_ms,
        )

    async def ban(
        self,
        app_id: int,
        dimension: ClockDimension,
        value: str,
        *,
        seconds: int,
        reason: str,
    ) -> None:
        """写入封禁。

        TTL 即剩余时长，不额外存过期时间戳——旧版存了 ``expire_at`` 又同时设
        TTL，两个真相来源需要手工对齐，读取时还要判断哪个为准。
        """
        if seconds <= 0:
            return
        key = ban_key(app_id, dimension, value)
        payload = orjson.dumps({"reason": reason, "dimension": dimension.value})
        try:
            await self._redis.set(key, payload, ex=seconds)
        except Exception as exc:
            _logger.error("clock_ban_failed", error=str(exc), app_id=app_id)

    async def unban(self, app_id: int, dimension: ClockDimension, value: str) -> None:
        try:
            await self._redis.delete(ban_key(app_id, dimension, value))
        except Exception as exc:
            _logger.error("clock_unban_failed", error=str(exc), app_id=app_id)

    async def get_limits(self, app_id: int) -> ClockLimits:
        """读取站点频控阈值，未配置则用默认值。

        ``app_id`` 是必需参数，调用方无法「忘记传」——旧版正是因为两个调用点
        都没传 app_id，站点自定义阈值链路彻底失效。
        """
        try:
            raw = await self._redis.get(limits_key(app_id))
        except Exception as exc:
            _logger.error("clock_limits_read_failed", error=str(exc), app_id=app_id)
            return default_limits(app_id)

        if not raw:
            return default_limits(app_id)
        try:
            return ClockLimits.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValueError) as exc:
            _logger.warning("clock_limits_invalid", error=str(exc), app_id=app_id)
            return default_limits(app_id)

    async def store_behavior(
        self,
        app_id: int,
        fingerprint: str,
        events: list[BehaviorEvent],
        *,
        now_ms: int,
    ) -> int:
        """写入行为时序，返回实际写入条数。

        score 用归一化后的**事件发生时间**而非接收时间，因此迟到事件会自动
        落到正确的时序位置——这就是乱序修复。写入后按 rank 裁剪，只保留最近
        :data:`BEHAVIOR_MAX_SEQUENCE` 条。
        """
        if not events:
            return 0

        key = behavior_key(app_id, fingerprint)
        mapping: dict[str, float] = {}
        for event in events:
            event_ts = normalize_event_time(event.client_ts_ms, server_now_ms=now_ms)
            member = make_member(event_ts, event.kind)
            payload = orjson.dumps(
                {
                    "kind": event.kind.value,
                    "ts": event_ts,
                    "data": event.data,
                }
            ).decode()
            mapping[f"{member}|{payload}"] = float(event_ts)

        try:
            pipe = self._redis.pipeline()
            pipe.zadd(key, mapping)
            # 负索引裁剪：保留最后 N 条（score 最大即最新）
            pipe.zremrangebyrank(key, 0, -(BEHAVIOR_MAX_SEQUENCE + 1))
            pipe.expire(key, BEHAVIOR_RETENTION_SECONDS)
            await pipe.execute()
        except Exception as exc:
            # 行为落库失败不影响决策：它当前不参与判定，只是分析素材。
            _logger.error("clock_behavior_store_failed", error=str(exc), app_id=app_id)
            return 0
        return len(mapping)

    async def read_behavior(
        self, app_id: int, fingerprint: str, *, limit: int = 200
    ) -> list[dict]:
        """按时序读回行为事件。

        供后续分析与排障使用。当前决策链路不调用它——但它必须是可用的，
        否则就会重演旧版「只写不读」的死代码。
        """
        key = behavior_key(app_id, fingerprint)
        try:
            members = await self._redis.zrange(key, -limit, -1)
        except Exception as exc:
            _logger.error("clock_behavior_read_failed", error=str(exc), app_id=app_id)
            return []

        out: list[dict] = []
        for member in members:
            text = member.decode() if isinstance(member, bytes) else str(member)
            _, _, payload = text.partition("|")
            if not payload:
                continue
            try:
                out.append(orjson.loads(payload))
            except orjson.JSONDecodeError:
                continue
        return out

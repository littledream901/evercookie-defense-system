"""Clock 存储测试：多窗口计数、封禁、行为时序乱序修复。

用内存 ZSet 模拟 Redis。重点验证三件旧版做错的事：
1. 同毫秒并发请求不能被 ZSet 静默去重
2. 一个 key 只能有一种类型，不能混用 ZSet 与 Hash
3. 行为时序按事件时间排序，迟到事件落到正确位置
"""

from __future__ import annotations

import pytest
from fangyu_shared.clock.behavior import (
    MAX_CLIENT_SKEW_MS,
    BehaviorKind,
    make_member,
    normalize_event_time,
)
from fangyu_shared.clock.windows import ClockDimension, rate_key
from fangyu_shared.schemas.clock import BehaviorEvent, ClockLimits
from src.infrastructure.clock.repository import ClockRepository

NOW_MS = 1_700_000_000_000


class _FakeZSet:
    """极简 ZSet：member → score。"""

    def __init__(self) -> None:
        self.data: dict[str, float] = {}


class _FakePipeline:
    def __init__(self, store: _FakeRedis) -> None:
        self._store = store
        self._ops: list[tuple] = []

    def zadd(self, key: str, mapping: dict[str, float]):
        self._ops.append(("zadd", key, mapping))
        return self

    def zremrangebyscore(self, key: str, lo, hi):
        self._ops.append(("zremrangebyscore", key, lo, hi))
        return self

    def zremrangebyrank(self, key: str, lo: int, hi: int):
        self._ops.append(("zremrangebyrank", key, lo, hi))
        return self

    def zcount(self, key: str, lo: float, hi: float):
        self._ops.append(("zcount", key, lo, hi))
        return self

    def expire(self, key: str, ttl: int):
        self._ops.append(("expire", key, ttl))
        return self

    def get(self, key: str):
        self._ops.append(("get", key))
        return self

    def ttl(self, key: str):
        self._ops.append(("ttl", key))
        return self

    async def execute(self) -> list:
        out: list = []
        for op in self._ops:
            out.append(self._store.apply(op))
        self._ops.clear()
        return out


class _FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, _FakeZSet] = {}
        self.strings: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    def _zset(self, key: str) -> _FakeZSet:
        if key in self.strings:
            raise TypeError("WRONGTYPE: key already holds a string")
        return self.zsets.setdefault(key, _FakeZSet())

    def apply(self, op: tuple):
        kind = op[0]
        if kind == "zadd":
            _, key, mapping = op
            self._zset(key).data.update(mapping)
            return len(mapping)
        if kind == "zremrangebyscore":
            _, key, lo, hi = op
            z = self._zset(key)
            hi_f = float(hi)
            removed = [m for m, s in z.data.items() if s <= hi_f]
            for m in removed:
                del z.data[m]
            return len(removed)
        if kind == "zremrangebyrank":
            _, key, lo, hi = op
            z = self._zset(key)
            ordered = sorted(z.data.items(), key=lambda kv: kv[1])
            n = len(ordered)
            idx_lo = lo if lo >= 0 else n + lo
            idx_hi = hi if hi >= 0 else n + hi
            removed = [m for i, (m, _) in enumerate(ordered) if idx_lo <= i <= idx_hi]
            for m in removed:
                del z.data[m]
            return len(removed)
        if kind == "zcount":
            _, key, lo, hi = op
            z = self._zset(key)
            return sum(1 for s in z.data.values() if float(lo) <= s <= float(hi))
        if kind == "expire":
            _, key, ttl = op
            self.ttls[key] = ttl
            return 1
        if kind == "get":
            return self.strings.get(op[1])
        if kind == "ttl":
            return self.ttls.get(op[1], -1)
        raise AssertionError(f"unhandled op {kind}")

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.strings[key] = value
        if ex:
            self.ttls[key] = ex

    async def get(self, key: str):
        return self.strings.get(key)

    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)

    async def zrange(self, key: str, lo: int, hi: int) -> list[str]:
        z = self.zsets.get(key)
        if z is None:
            return []
        ordered = [m for m, _ in sorted(z.data.items(), key=lambda kv: kv[1])]
        n = len(ordered)
        idx_lo = lo if lo >= 0 else max(0, n + lo)
        idx_hi = hi if hi >= 0 else n + hi
        return ordered[idx_lo : idx_hi + 1]


@pytest.fixture
def redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def repo(redis: _FakeRedis) -> ClockRepository:
    return ClockRepository(redis)  # type: ignore[arg-type]


# ---------- 计数 ----------
@pytest.mark.asyncio
async def test_first_request_counts_itself(repo: ClockRepository) -> None:
    """本次访问计入返回的计数，判定用 > 比较即「第 N+1 次才超限」。"""
    reading = await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.count_for("burst") == 1
    assert reading.fingerprint.count_for("burst") == 1


@pytest.mark.asyncio
async def test_same_millisecond_requests_both_counted(repo: ClockRepository) -> None:
    """同毫秒的两次请求必须各计一次。

    旧版 member 用「毫秒取模」当序号，同毫秒的两条记录 member 相同而被 ZSet
    静默去重，突发流量因此被少计。
    """
    for _ in range(5):
        reading = await repo.touch_and_read(
            1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
        )
    assert reading.ip.count_for("burst") == 5


@pytest.mark.asyncio
async def test_windows_computed_from_single_zset(
    repo: ClockRepository, redis: _FakeRedis
) -> None:
    """多窗口从同一份数据算出，只有一个 key。"""
    await repo.touch_and_read(1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS)
    key = rate_key(1, ClockDimension.IP, "iphash")
    assert key in redis.zsets
    # 该 key 不能同时是 string——旧版正是在同一 key 上混用 ZSet 与 Hash
    assert key not in redis.strings


@pytest.mark.asyncio
async def test_old_events_fall_out_of_narrow_window(repo: ClockRepository) -> None:
    """15 秒前的访问不计入 10 秒 burst 窗口，但仍计入 60 秒 short 窗口。"""
    await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS - 15_000
    )
    reading = await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.count_for("burst") == 1
    assert reading.ip.count_for("short") == 2


@pytest.mark.asyncio
async def test_dimensions_counted_independently(repo: ClockRepository) -> None:
    """换 IP 但同指纹时，指纹计数继续累加。"""
    await repo.touch_and_read(1, ip_hash="ip_a", fingerprint="fp", now_ms=NOW_MS)
    reading = await repo.touch_and_read(
        1, ip_hash="ip_b", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.count_for("burst") == 1
    assert reading.fingerprint.count_for("burst") == 2


@pytest.mark.asyncio
async def test_apps_isolated(repo: ClockRepository) -> None:
    await repo.touch_and_read(1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS)
    reading = await repo.touch_and_read(
        2, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.count_for("burst") == 1


# ---------- 封禁 ----------
@pytest.mark.asyncio
async def test_ban_then_read(repo: ClockRepository) -> None:
    await repo.ban(
        1, ClockDimension.IP, "iphash", seconds=600, reason="rate_limit:ip:burst"
    )
    reading = await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.ban.banned is True
    assert reading.ip.ban.reason == "rate_limit:ip:burst"
    assert reading.ip.ban.ttl_seconds == 600


@pytest.mark.asyncio
async def test_unban_clears_state(repo: ClockRepository) -> None:
    await repo.ban(1, ClockDimension.IP, "iphash", seconds=600, reason="x")
    await repo.unban(1, ClockDimension.IP, "iphash")
    reading = await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.ban.banned is False


@pytest.mark.asyncio
async def test_zero_duration_ban_is_noop(repo: ClockRepository) -> None:
    await repo.ban(1, ClockDimension.IP, "iphash", seconds=0, reason="x")
    reading = await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.ban.banned is False


# ---------- 阈值配置 ----------
@pytest.mark.asyncio
async def test_limits_default_when_unset(repo: ClockRepository) -> None:
    limits = await repo.get_limits(42)
    assert limits.app_id == 42
    assert limits.enabled is True


@pytest.mark.asyncio
async def test_limits_read_from_redis(repo: ClockRepository, redis: _FakeRedis) -> None:
    import orjson
    from fangyu_shared.clock.windows import limits_key

    redis.strings[limits_key(7)] = orjson.dumps(
        {"appId": 7, "windows": {"burst": 3}, "banSeconds": 60}
    )
    limits = await repo.get_limits(7)
    assert limits.windows["burst"] == 3
    assert limits.ban_seconds == 60


@pytest.mark.asyncio
async def test_corrupt_limits_fall_back_to_default(
    repo: ClockRepository, redis: _FakeRedis
) -> None:
    """脏配置不能让频控整体失效。"""
    from fangyu_shared.clock.windows import limits_key

    redis.strings[limits_key(7)] = b"{not json"
    limits = await repo.get_limits(7)
    assert limits == ClockLimits(appId=7)


# ---------- 行为时序：乱序修复 ----------
@pytest.mark.asyncio
async def test_behavior_stored_in_event_order_not_arrival_order(
    repo: ClockRepository,
) -> None:
    """迟到事件按事件时间落位，而非到达顺序。

    这是乱序修复的核心断言：先提交 t=300 的事件，再提交 t=100 的事件，
    读回时 t=100 必须排在前面。
    """
    await repo.store_behavior(
        1,
        "fp",
        [BehaviorEvent(kind=BehaviorKind.CLICK, clientTsMs=NOW_MS + 300)],
        now_ms=NOW_MS,
    )
    await repo.store_behavior(
        1,
        "fp",
        [BehaviorEvent(kind=BehaviorKind.SCROLL, clientTsMs=NOW_MS + 100)],
        now_ms=NOW_MS,
    )
    events = await repo.read_behavior(1, "fp")
    assert [e["kind"] for e in events] == ["scroll", "click"]


@pytest.mark.asyncio
async def test_behavior_roundtrip_preserves_data(repo: ClockRepository) -> None:
    written = await repo.store_behavior(
        1,
        "fp",
        [BehaviorEvent(kind=BehaviorKind.CLICK, clientTsMs=NOW_MS, data={"x": 10, "y": 20})],
        now_ms=NOW_MS,
    )
    assert written == 1
    events = await repo.read_behavior(1, "fp")
    assert events[0]["data"] == {"x": 10, "y": 20}


@pytest.mark.asyncio
async def test_empty_behavior_list_is_noop(repo: ClockRepository) -> None:
    assert await repo.store_behavior(1, "fp", [], now_ms=NOW_MS) == 0


@pytest.mark.asyncio
async def test_same_millisecond_behavior_events_not_deduped(
    repo: ClockRepository,
) -> None:
    """同毫秒同类型的多条事件必须都保留（旧版会被 ZSet 去重吞掉）。"""
    events = [
        BehaviorEvent(kind=BehaviorKind.MOUSE_MOVE, clientTsMs=NOW_MS),
        BehaviorEvent(kind=BehaviorKind.MOUSE_MOVE, clientTsMs=NOW_MS),
        BehaviorEvent(kind=BehaviorKind.MOUSE_MOVE, clientTsMs=NOW_MS),
    ]
    assert await repo.store_behavior(1, "fp", events, now_ms=NOW_MS) == 3
    assert len(await repo.read_behavior(1, "fp")) == 3


# ---------- 时间归一化 ----------
def test_future_timestamp_clamped_to_server_time() -> None:
    """客户端谎报未来时间必须被夹取，否则可操纵排序挤掉真实事件。"""
    far_future = NOW_MS + MAX_CLIENT_SKEW_MS * 10
    assert normalize_event_time(far_future, server_now_ms=NOW_MS) == NOW_MS


def test_ancient_timestamp_clamped() -> None:
    assert normalize_event_time(1, server_now_ms=NOW_MS) == NOW_MS


def test_timestamp_within_skew_preserved() -> None:
    ts = NOW_MS - 1000
    assert normalize_event_time(ts, server_now_ms=NOW_MS) == ts


def test_zero_timestamp_uses_server_time() -> None:
    assert normalize_event_time(0, server_now_ms=NOW_MS) == NOW_MS


def test_member_unique_per_call() -> None:
    a = make_member(NOW_MS, BehaviorKind.CLICK)
    b = make_member(NOW_MS, BehaviorKind.CLICK)
    assert a != b


# ---------- Redis 故障降级 ----------
@pytest.mark.asyncio
async def test_redis_failure_returns_empty_reading() -> None:
    """频控不可用时放行，而不是把 Redis 故障升级为全站不可访问。"""

    class _BrokenRedis:
        def pipeline(self):
            raise ConnectionError("redis down")

    repo = ClockRepository(_BrokenRedis())  # type: ignore[arg-type]
    reading = await repo.touch_and_read(
        1, ip_hash="iphash", fingerprint="fp", now_ms=NOW_MS
    )
    assert reading.ip.count_for("burst") == 0
    assert reading.active_ban is None

"""封禁列表与批量解除的单元测试。

重点覆盖游标语义：``SCAN`` 每批返回条数是近似值，中间批次返回 0 条也正常。
用条目数判断结束会提前截断列表，而运维只会看到「封禁列表少了几条」，不会
意识到是翻页逻辑的问题。
"""

from __future__ import annotations

import orjson
import pytest
from fangyu_shared.clock.windows import (
    ClockDimension,
    ban_key,
    ban_scan_pattern,
    parse_ban_key,
)
from src.infrastructure.clock_sync import ClockSync


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def get(self, key: str) -> None:
        self._ops.append(("get", key))

    def ttl(self, key: str) -> None:
        self._ops.append(("ttl", key))

    async def execute(self) -> list:
        out: list = []
        for op, key in self._ops:
            if op == "get":
                out.append(self._redis.store.get(key))
            else:
                out.append(self._redis.ttls.get(key, -1))
        self._ops.clear()
        return out


class _FakeRedis:
    """内存 KV 替身，SCAN 按固定批大小切分以模拟游标语义。"""

    def __init__(self, *, batch: int = 2) -> None:
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self._batch = batch
        self.scan_calls: list[tuple[int, str]] = []

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)

    async def scan(self, cursor: int = 0, match: str | None = None, count: int = 10):
        self.scan_calls.append((cursor, match or ""))
        keys = sorted(self.store)
        if match:
            prefix = match.rstrip("*")
            keys = [k for k in keys if k.startswith(prefix)]
        chunk = keys[cursor : cursor + self._batch]
        next_cursor = cursor + self._batch
        if next_cursor >= len(keys):
            next_cursor = 0
        return next_cursor, chunk

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                self.ttls.pop(key, None)
                removed += 1
        return removed


def _seed(redis: _FakeRedis, app_id: int, dim: ClockDimension, value: str, *, ttl: int = 900) -> None:
    key = ban_key(app_id, dim, value)
    redis.store[key] = orjson.dumps({"reason": "rate_limit:ip:burst", "dimension": dim.value})
    redis.ttls[key] = ttl


@pytest.fixture
def sync() -> tuple[ClockSync, _FakeRedis]:
    redis = _FakeRedis()
    return ClockSync(redis), redis  # type: ignore[arg-type]


# ---------- 键构造与解析 ----------
def test_scan_pattern_scopes_to_app() -> None:
    assert ban_scan_pattern(7) == "fangyu:clock:ban:7:*"
    assert ban_scan_pattern(7, ClockDimension.IP) == "fangyu:clock:ban:7:ip:*"


def test_parse_ban_key_roundtrip() -> None:
    key = ban_key(7, ClockDimension.FINGERPRINT, "fp_abc")
    assert parse_ban_key(key) == (7, ClockDimension.FINGERPRINT, "fp_abc")


def test_parse_ban_key_keeps_colons_in_value() -> None:
    key = ban_key(7, ClockDimension.FINGERPRINT, "a:b:c")
    assert parse_ban_key(key) == (7, ClockDimension.FINGERPRINT, "a:b:c")


def test_parse_ban_key_rejects_foreign_keys() -> None:
    """不能把频控计数键或别的命名空间误当封禁列出来。"""
    assert parse_ban_key("fangyu:clock:rate:7:ip:abc") is None
    assert parse_ban_key("other:clock:ban:7:ip:abc") is None
    assert parse_ban_key("fangyu:clock:ban:7:ip:") is None
    assert parse_ban_key("fangyu:clock:ban:notanint:ip:abc") is None
    assert parse_ban_key("fangyu:clock:ban:7:zz:abc") is None


# ---------- 扫描 ----------
@pytest.mark.asyncio
async def test_scan_returns_entries_with_ttl(sync) -> None:
    svc, redis = sync
    _seed(redis, 1, ClockDimension.IP, "hash_a", ttl=600)

    cursor, entries = await svc.scan_bans(1)

    assert cursor == 0
    assert entries == [
        {
            "dimension": "ip",
            "value": "hash_a",
            "reason": "rate_limit:ip:burst",
            "ttlSeconds": 600,
        }
    ]


@pytest.mark.asyncio
async def test_scan_paginates_via_cursor(sync) -> None:
    """批大小 2、共 5 条：必须靠游标翻完，不能靠条目数判断结束。"""
    svc, redis = sync
    for i in range(5):
        _seed(redis, 1, ClockDimension.IP, f"hash_{i}")

    seen: list[str] = []
    cursor = 0
    for _ in range(10):
        cursor, entries = await svc.scan_bans(1, cursor=cursor)
        seen.extend(e["value"] for e in entries)
        if cursor == 0:
            break

    assert sorted(seen) == [f"hash_{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_scan_filters_by_dimension(sync) -> None:
    svc, redis = sync
    _seed(redis, 1, ClockDimension.IP, "hash_a")
    _seed(redis, 1, ClockDimension.FINGERPRINT, "fp_a")

    _, entries = await svc.scan_bans(1, dimension=ClockDimension.FINGERPRINT)

    assert [e["dimension"] for e in entries] == ["fp"]


@pytest.mark.asyncio
async def test_scan_scoped_to_app(sync) -> None:
    svc, redis = sync
    _seed(redis, 1, ClockDimension.IP, "hash_a")
    _seed(redis, 2, ClockDimension.IP, "hash_b")

    _, entries = await svc.scan_bans(2)

    assert [e["value"] for e in entries] == ["hash_b"]


@pytest.mark.asyncio
async def test_scan_skips_key_expired_mid_flight(sync) -> None:
    """扫描与取值之间到期是正常竞态，不该让接口在攻击高峰随机失败。"""
    svc, redis = sync
    _seed(redis, 1, ClockDimension.IP, "hash_a")
    key = ban_key(1, ClockDimension.IP, "hash_a")
    redis.store[key] = None  # type: ignore[assignment]

    _, entries = await svc.scan_bans(1)

    assert entries == []


@pytest.mark.asyncio
async def test_scan_tolerates_broken_meta(sync) -> None:
    svc, redis = sync
    key = ban_key(1, ClockDimension.IP, "hash_a")
    redis.store[key] = b"not-json"
    redis.ttls[key] = 30

    _, entries = await svc.scan_bans(1)

    assert entries[0]["reason"] == ""
    assert entries[0]["ttlSeconds"] == 30


@pytest.mark.asyncio
async def test_scan_empty_returns_no_entries(sync) -> None:
    svc, _ = sync
    cursor, entries = await svc.scan_bans(1)
    assert (cursor, entries) == (0, [])


@pytest.mark.asyncio
async def test_scan_negative_ttl_clamped(sync) -> None:
    """``TTL`` 对无过期键返回 -1，不能把它渲染成负数剩余时长。"""
    svc, redis = sync
    key = ban_key(1, ClockDimension.IP, "hash_a")
    redis.store[key] = orjson.dumps({"reason": "manual"})
    redis.ttls[key] = -1

    _, entries = await svc.scan_bans(1)

    assert entries[0]["ttlSeconds"] == 0


# ---------- 批量解封 ----------
@pytest.mark.asyncio
async def test_unban_many_removes_all(sync) -> None:
    svc, redis = sync
    _seed(redis, 1, ClockDimension.IP, "hash_a")
    _seed(redis, 1, ClockDimension.FINGERPRINT, "fp_a")

    removed = await svc.unban_many(
        1, [(ClockDimension.IP, "hash_a"), (ClockDimension.FINGERPRINT, "fp_a")]
    )

    assert removed == 2
    assert redis.store == {}


@pytest.mark.asyncio
async def test_unban_many_counts_only_existing(sync) -> None:
    """requested 与 removed 的差值让调用方能区分「解封成功」与「值写错了」。"""
    svc, redis = sync
    _seed(redis, 1, ClockDimension.IP, "hash_a")

    removed = await svc.unban_many(
        1, [(ClockDimension.IP, "hash_a"), (ClockDimension.IP, "nope")]
    )

    assert removed == 1


@pytest.mark.asyncio
async def test_unban_many_empty_skips_redis(sync) -> None:
    """空列表不能落到 ``DEL`` ——不带 key 的 DEL 是语法错误。"""
    svc, _ = sync
    assert await svc.unban_many(1, []) == 0

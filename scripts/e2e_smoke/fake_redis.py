"""进程内 Redis 替身，用于无 Docker 环境下的端到端冒烟。

只实现本项目实际使用的命令（见 scripts/e2e_smoke/README 的命令清单），
刻意保持以下与真实 Redis 一致的语义，否则会掩盖真实缺陷：

1. 读取一律返回 ``str``。生产配置 ``RedisConfig.decode_responses`` 恒为 True，
   若替身返回 bytes，会让「拿 bytes 和 str 比较」这类缺陷在冒烟里蒙混过关。
2. ``rename`` 源键不存在时抛 ``ResponseError``。admin 侧的 staging→live 原子
   换页正是靠「空集合不走 rename」规避这一点，替身若静默成功就测不出来。
3. TTL 到期真实驱逐，且 ``ttl()`` 返回 int。Clock 的封禁剩余时间靠它判定。
"""

from __future__ import annotations

import fnmatch
import time
from typing import Any

from redis.exceptions import ResponseError


def _norm(value: Any) -> str:
    """写入归一化：bytes → str。

    生产侧 decode_responses=True，写 bytes 读回来也是 str。替身必须复现这个
    不对称，否则 challenge_pass_store 那类「写 b'trusted' 读 str」的缺陷会被藏住。
    """
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class FakeRedis:
    """单进程内存 Redis。非线程安全，仅供单事件循环的冒烟脚本使用。"""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.expiry: dict[str, float] = {}
        self.command_log: list[str] = []

    # ── 过期与内部工具 ───────────────────────────────────────────────
    def _expired(self, key: str) -> bool:
        exp = self.expiry.get(key)
        if exp is None:
            return False
        if exp <= time.time():
            self._drop(key)
            return True
        return False

    def _drop(self, key: str) -> None:
        self.kv.pop(key, None)
        self.hashes.pop(key, None)
        self.sets.pop(key, None)
        self.zsets.pop(key, None)
        self.streams.pop(key, None)
        self.expiry.pop(key, None)

    def _exists_any(self, key: str) -> bool:
        if self._expired(key):
            return False
        return (
            key in self.kv
            or key in self.hashes
            or key in self.sets
            or key in self.zsets
            or key in self.streams
        )

    def _log(self, name: str) -> None:
        self.command_log.append(name)

    # ── 字符串 ──────────────────────────────────────────────────────
    async def set(
        self,
        key: str,
        value: Any,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        self._log("set")
        self._expired(key)
        if nx and key in self.kv:
            return None
        self.kv[key] = _norm(value)
        if ex is not None:
            self.expiry[key] = time.time() + int(ex)
        return True

    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        self._log("setex")
        self.kv[key] = _norm(value)
        self.expiry[key] = time.time() + int(ttl)
        return True

    async def get(self, key: str) -> str | None:
        self._log("get")
        if self._expired(key):
            return None
        return self.kv.get(key)

    async def delete(self, *keys: str) -> int:
        self._log("delete")
        removed = 0
        for key in keys:
            if self._exists_any(key):
                removed += 1
            self._drop(key)
        return removed

    async def expire(self, key: str, ttl: int) -> bool:
        self._log("expire")
        if not self._exists_any(key):
            return False
        self.expiry[key] = time.time() + int(ttl)
        return True

    async def ttl(self, key: str) -> int:
        """返回剩余秒数。-2 = 键不存在，-1 = 无 TTL，与真实 Redis 一致。"""
        self._log("ttl")
        if not self._exists_any(key):
            return -2
        exp = self.expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - time.time()))

    async def incr(self, key: str) -> int:
        self._log("incr")
        self._expired(key)
        cur = int(self.kv.get(key, "0")) + 1
        self.kv[key] = str(cur)
        return cur

    async def rename(self, src: str, dst: str) -> bool:
        """源键不存在时抛错——真实 Redis 语义，不能静默成功。"""
        self._log("rename")
        if not self._exists_any(src):
            raise ResponseError("no such key")
        for bucket in (self.kv, self.hashes, self.sets, self.zsets, self.streams):
            if src in bucket:
                bucket[dst] = bucket.pop(src)  # type: ignore[assignment]
        if src in self.expiry:
            self.expiry[dst] = self.expiry.pop(src)
        else:
            self.expiry.pop(dst, None)
        return True

    async def ping(self) -> bool:
        self._log("ping")
        return True

    async def scan(
        self,
        cursor: int = 0,
        *,
        match: str | None = None,
        count: int = 10,
    ) -> tuple[int, list[str]]:
        """一次性返回全部匹配键，游标恒为 0（替身无需分页）。"""
        self._log("scan")
        keys = [k for k in list(self.kv) if not self._expired(k)]
        if match:
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        return 0, keys

    # ── Hash ────────────────────────────────────────────────────────
    async def hset(
        self,
        key: str,
        field: Any = None,
        value: Any = None,
        *,
        mapping: dict[Any, Any] | None = None,
    ) -> int:
        self._log("hset")
        self._expired(key)
        bucket = self.hashes.setdefault(key, {})
        written = 0
        if mapping is not None:
            for k, v in mapping.items():
                bucket[_norm(k)] = _norm(v)
                written += 1
        if field is not None:
            bucket[_norm(field)] = _norm(value)
            written += 1
        return written

    async def hget(self, key: str, field: Any) -> str | None:
        self._log("hget")
        if self._expired(key):
            return None
        return self.hashes.get(key, {}).get(_norm(field))

    async def hgetall(self, key: str) -> dict[str, str]:
        self._log("hgetall")
        if self._expired(key):
            return {}
        return dict(self.hashes.get(key, {}))

    async def hmget(self, key: str, fields: list[Any]) -> list[str | None]:
        self._log("hmget")
        if self._expired(key):
            return [None for _ in fields]
        bucket = self.hashes.get(key, {})
        return [bucket.get(_norm(f)) for f in fields]

    async def hdel(self, key: str, *fields: Any) -> int:
        self._log("hdel")
        bucket = self.hashes.get(key)
        if not bucket:
            return 0
        removed = 0
        for f in fields:
            if bucket.pop(_norm(f), None) is not None:
                removed += 1
        return removed

    async def hlen(self, key: str) -> int:
        self._log("hlen")
        if self._expired(key):
            return 0
        return len(self.hashes.get(key, {}))

    # ── Set ─────────────────────────────────────────────────────────
    async def sadd(self, key: str, *members: Any) -> int:
        self._log("sadd")
        self._expired(key)
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(_norm(m) for m in members)
        return len(bucket) - before

    async def srem(self, key: str, *members: Any) -> int:
        self._log("srem")
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        before = len(bucket)
        for m in members:
            bucket.discard(_norm(m))
        return before - len(bucket)

    async def sismember(self, key: str, member: Any) -> bool:
        self._log("sismember")
        if self._expired(key):
            return False
        return _norm(member) in self.sets.get(key, set())

    async def scard(self, key: str) -> int:
        self._log("scard")
        if self._expired(key):
            return 0
        return len(self.sets.get(key, set()))

    # ── ZSet ────────────────────────────────────────────────────────
    async def zadd(self, key: str, mapping: dict[Any, float]) -> int:
        self._log("zadd")
        self._expired(key)
        bucket = self.zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            m = _norm(member)
            if m not in bucket:
                added += 1
            bucket[m] = float(score)
        return added

    @staticmethod
    def _bound(raw: Any) -> float:
        if raw == "-inf":
            return float("-inf")
        if raw == "+inf":
            return float("inf")
        return float(raw)

    async def zremrangebyscore(self, key: str, lo: Any, hi: Any) -> int:
        self._log("zremrangebyscore")
        bucket = self.zsets.get(key)
        if not bucket:
            return 0
        low, high = self._bound(lo), self._bound(hi)
        doomed = [m for m, s in bucket.items() if low <= s <= high]
        for m in doomed:
            bucket.pop(m, None)
        return len(doomed)

    async def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        self._log("zremrangebyrank")
        bucket = self.zsets.get(key)
        if not bucket:
            return 0
        ordered = [m for m, _ in sorted(bucket.items(), key=lambda kv: kv[1])]
        doomed = ordered[start : stop + 1] if stop >= 0 else ordered[start : len(ordered) + stop + 1]
        for m in doomed:
            bucket.pop(m, None)
        return len(doomed)

    async def zcount(self, key: str, lo: Any, hi: Any) -> int:
        self._log("zcount")
        if self._expired(key):
            return 0
        bucket = self.zsets.get(key, {})
        low, high = self._bound(lo), self._bound(hi)
        return sum(1 for s in bucket.values() if low <= s <= high)

    async def zcard(self, key: str) -> int:
        self._log("zcard")
        if self._expired(key):
            return 0
        return len(self.zsets.get(key, {}))

    async def zrange(self, key: str, start: int, stop: int) -> list[str]:
        self._log("zrange")
        if self._expired(key):
            return []
        bucket = self.zsets.get(key, {})
        ordered = [m for m, _ in sorted(bucket.items(), key=lambda kv: kv[1])]
        if stop == -1:
            return ordered[start:]
        return ordered[start : stop + 1]

    # ── Stream ──────────────────────────────────────────────────────
    async def xadd(
        self,
        name: str,
        fields: dict[Any, Any] | None = None,
        *,
        maxlen: int | None = None,
        approximate: bool = True,
        **kwargs: Any,
    ) -> str:
        self._log("xadd")
        payload = fields if fields is not None else kwargs.get("fields", {})
        bucket = self.streams.setdefault(name, [])
        entry_id = f"{int(time.time() * 1000)}-{len(bucket)}"
        bucket.append((entry_id, {_norm(k): _norm(v) for k, v in payload.items()}))
        if maxlen is not None and len(bucket) > maxlen:
            del bucket[: len(bucket) - maxlen]
        return entry_id

    # ── Pipeline ────────────────────────────────────────────────────
    def pipeline(self, transaction: bool = True) -> FakePipeline:
        self._log("pipeline")
        return FakePipeline(self)


class FakePipeline:
    """命令入队后由 execute() 顺序执行，返回值按入队顺序排列。

    入队方法是同步的（生产代码不 await 入队），且必须支持 ``async with``——
    admin 侧有 5 处用 ``async with redis.pipeline(transaction=False)``。
    """

    def __init__(self, client: FakeRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self) -> FakePipeline:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        self._ops.clear()

    def _queue(self, name: str, *args: Any, **kwargs: Any) -> FakePipeline:
        self._ops.append((name, args, kwargs))
        return self

    def __getattr__(self, name: str):
        # 入队任何 FakeRedis 支持的命令，避免逐个转发样板代码。
        if not hasattr(FakeRedis, name):
            raise AttributeError(name)

        def _enqueue(*args: Any, **kwargs: Any) -> FakePipeline:
            return self._queue(name, *args, **kwargs)

        return _enqueue

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args, kwargs in self._ops:
            method = getattr(self._client, name)
            results.append(await method(*args, **kwargs))
        self._ops.clear()
        return results

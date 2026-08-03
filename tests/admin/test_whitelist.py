"""白名单写入侧单元测试。

重点覆盖 IP 规范化：admin 存的 field 与 gateway 查的 field 对不上时，白名单
写了但永不命中，且两侧日志都没有任何异常——这是最难排查的失效形态。
"""

from __future__ import annotations

import orjson
import pytest
from fangyu_shared.whitelist.keys import WhitelistDimension
from src.application.services.whitelist_service import (
    MAX_ENTRIES_PER_APP,
    WhitelistError,
    WhitelistService,
)
from src.infrastructure.whitelist_sync import WhitelistSync


class _FakeRedis:
    """内存 Hash 替身。只实现白名单用到的命令。"""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, bytes]] = {}

    async def hset(self, key: str, field: str, value: bytes) -> int:
        h = self.store.setdefault(key, {})
        existed = field in h
        h[field] = value
        return 0 if existed else 1

    async def hdel(self, key: str, field: str) -> int:
        h = self.store.get(key, {})
        return 1 if h.pop(field, None) is not None else 0

    async def hget(self, key: str, field: str):
        return self.store.get(key, {}).get(field)

    async def hgetall(self, key: str):
        return dict(self.store.get(key, {}))

    async def hlen(self, key: str) -> int:
        return len(self.store.get(key, {}))

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed


@pytest.fixture
def service() -> tuple[WhitelistService, _FakeRedis]:
    redis = _FakeRedis()
    return WhitelistService(WhitelistSync(redis)), redis  # type: ignore[arg-type]


# ---------- IP 规范化 ----------
@pytest.mark.asyncio
async def test_ip_stored_under_compressed_form(service) -> None:
    """gateway 用 str(ctx.ip)（压缩表示）查表，admin 必须存同一形状。"""
    svc, redis = service
    await svc.add(1, WhitelistDimension.IP, "2001:0db8:0000:0000:0000:0000:0000:0001")

    fields = list(redis.store["fangyu:whitelist:1"])
    assert fields == ["ip:2001:db8::1"]


@pytest.mark.asyncio
async def test_ipv4_leading_zeros_rejected(service) -> None:
    """``1.2.3.004`` 在不同解析器下含义不同，直接拒绝而非猜测。"""
    svc, _ = service
    with pytest.raises(WhitelistError):
        await svc.add(1, WhitelistDimension.IP, "1.2.3.004")


@pytest.mark.asyncio
async def test_ip_whitespace_trimmed(service) -> None:
    svc, redis = service
    await svc.add(1, WhitelistDimension.IP, "  203.0.113.7  ")
    assert "ip:203.0.113.7" in redis.store["fangyu:whitelist:1"]


@pytest.mark.asyncio
async def test_invalid_ip_rejected(service) -> None:
    svc, _ = service
    with pytest.raises(WhitelistError):
        await svc.add(1, WhitelistDimension.IP, "not-an-ip")


@pytest.mark.asyncio
async def test_empty_value_rejected(service) -> None:
    svc, _ = service
    with pytest.raises(WhitelistError):
        await svc.add(1, WhitelistDimension.FINGERPRINT, "   ")


@pytest.mark.asyncio
async def test_overlong_fingerprint_rejected(service) -> None:
    svc, _ = service
    with pytest.raises(WhitelistError):
        await svc.add(1, WhitelistDimension.FINGERPRINT, "x" * 129)


@pytest.mark.asyncio
async def test_remove_normalizes_too(service) -> None:
    """录入与删除的规范化必须一致，否则删不掉自己刚加的条目。"""
    svc, _ = service
    await svc.add(1, WhitelistDimension.IP, "2001:0db8::0001")

    assert await svc.remove(1, WhitelistDimension.IP, "2001:db8::1") is True


# ---------- 元信息与列表 ----------
@pytest.mark.asyncio
async def test_meta_persisted(service) -> None:
    svc, redis = service
    entry = await svc.add(
        1, WhitelistDimension.IP, "203.0.113.7", note="办公网", created_by="42"
    )

    assert entry["note"] == "办公网"
    assert entry["createdBy"] == "42"
    assert entry["createdAtMs"] > 0

    raw = redis.store["fangyu:whitelist:1"]["ip:203.0.113.7"]
    assert orjson.loads(raw)["note"] == "办公网"


@pytest.mark.asyncio
async def test_list_returns_both_dimensions(service) -> None:
    svc, _ = service
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7")
    await svc.add(1, WhitelistDimension.FINGERPRINT, "fp_abc")

    entries = await svc.list_entries(1)

    assert {(e["dimension"], e["value"]) for e in entries} == {
        ("ip", "203.0.113.7"),
        ("fp", "fp_abc"),
    }


@pytest.mark.asyncio
async def test_list_skips_dirty_field(service) -> None:
    """脏 field 跳过而非 500，否则运维连清理它的列表页都打不开。"""
    svc, redis = service
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7")
    redis.store["fangyu:whitelist:1"]["garbage"] = b"{}"

    entries = await svc.list_entries(1)

    assert len(entries) == 1


@pytest.mark.asyncio
async def test_list_tolerates_broken_meta(service) -> None:
    svc, redis = service
    redis.store["fangyu:whitelist:1"] = {"ip:203.0.113.7": b"not-json"}

    entries = await svc.list_entries(1)

    assert entries[0]["value"] == "203.0.113.7"
    assert entries[0]["note"] == ""


@pytest.mark.asyncio
async def test_apps_are_isolated(service) -> None:
    svc, _ = service
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7")

    assert await svc.list_entries(2) == []


# ---------- 上限 ----------
@pytest.mark.asyncio
async def test_entry_cap_enforced(service) -> None:
    """无上限时批量灌入会让走 HGETALL 的列表接口阻塞 Redis。"""
    svc, redis = service
    redis.store["fangyu:whitelist:1"] = {
        f"fp:x{i}": b"{}" for i in range(MAX_ENTRIES_PER_APP)
    }

    with pytest.raises(WhitelistError):
        await svc.add(1, WhitelistDimension.FINGERPRINT, "one_more")


@pytest.mark.asyncio
async def test_existing_entry_updatable_at_cap(service) -> None:
    """满额后仍能改已有条目的备注，否则连清理说明都写不了。"""
    svc, redis = service
    redis.store["fangyu:whitelist:1"] = {
        f"fp:x{i}": b"{}" for i in range(MAX_ENTRIES_PER_APP)
    }

    entry = await svc.add(1, WhitelistDimension.FINGERPRINT, "x0", note="待清理")

    assert entry["note"] == "待清理"


# ---------- 覆盖与清空 ----------
@pytest.mark.asyncio
async def test_duplicate_add_updates_note(service) -> None:
    """重复提交视为改备注：报错没有意义，更新才是真实意图。"""
    svc, _ = service
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7", note="旧")
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7", note="新")

    entries = await svc.list_entries(1)
    assert len(entries) == 1
    assert entries[0]["note"] == "新"


@pytest.mark.asyncio
async def test_remove_missing_returns_false(service) -> None:
    svc, _ = service
    assert await svc.remove(1, WhitelistDimension.IP, "203.0.113.7") is False


@pytest.mark.asyncio
async def test_clear_returns_count(service) -> None:
    svc, _ = service
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7")
    await svc.add(1, WhitelistDimension.FINGERPRINT, "fp_abc")

    assert await svc.clear(1) == 2
    assert await svc.list_entries(1) == []


@pytest.mark.asyncio
async def test_clear_empty_is_zero(service) -> None:
    svc, _ = service
    assert await svc.clear(1) == 0


@pytest.mark.asyncio
async def test_no_ttl_set_on_whitelist(service) -> None:
    """白名单是配置不是缓存：过期后无人重建会让误封访客再次被拦。

    ``_FakeRedis`` 不实现 ``expire``/``set(ex=)``，若实现里加了 TTL 这条会
    因 AttributeError 失败——这正是想要的信号。
    """
    svc, redis = service
    await svc.add(1, WhitelistDimension.IP, "203.0.113.7")
    assert not hasattr(redis, "_expirations")

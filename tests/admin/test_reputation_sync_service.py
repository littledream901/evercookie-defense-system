"""admin 侧声誉同步（手动触发）单元测试。

``ReputationSyncService`` 与 ``worker.ReputationWriter`` 现在都是
``fangyu_shared.reputation.ReputationSyncer`` 的薄封装，不再各存一份复制的
SQL 与评分公式。这里仍然从**入口类**测一遍而不是只测 shared：两个封装各自
负责翻译配置与结果结构，写错了一样会让同步静默失真。

分数表与 ``tests/worker/test_reputation_writer.py`` 保持一致——它们现在验证
的是同一个 ``calc_score``，重复一遍的成本极低，而一旦哪天又有人把公式复制
回某一侧，这两个文件里必有一个先失败。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fangyu_shared.reputation import calc_score as _calc_score
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile
from src.application.services.reputation_sync_service import ReputationSyncService


class _FakeClickHouse:
    """按 SQL 内容分派返回行的 ClickHouse 替身。"""

    def __init__(
        self,
        *,
        ip_rows: list[dict] | None = None,
        device_rows: list[dict] | None = None,
        ip_fails: bool = False,
        device_fails: bool = False,
    ) -> None:
        self._ip_rows = ip_rows or []
        self._device_rows = device_rows or []
        self._ip_fails = ip_fails
        self._device_fails = device_fails
        self.queries: list[str] = []

    async def fetch(self, sql: str, params: dict | None = None) -> list[dict]:
        self.queries.append(sql)
        if "mv_ip_reputation_daily" in sql:
            if self._ip_fails:
                raise ConnectionError("clickhouse down")
            return self._ip_rows
        if self._device_fails:
            raise ConnectionError("clickhouse down")
        return self._device_rows


class _FakeCache:
    def __init__(
        self,
        *,
        ips: dict[tuple[int, str], IpProfile] | None = None,
        devices: dict[tuple[int, str], DeviceProfile] | None = None,
        set_ip_fails: bool = False,
    ) -> None:
        self.ips = ips or {}
        self.devices = devices or {}
        self._set_ip_fails = set_ip_fails
        self.written_ips: list[tuple[int, IpProfile]] = []
        self.written_devices: list[tuple[int, DeviceProfile]] = []

    async def get_ip(self, app_id: int, ip: str) -> IpProfile | None:
        return self.ips.get((app_id, ip))

    async def set_ip(self, app_id: int, profile: IpProfile) -> None:
        if self._set_ip_fails:
            raise ConnectionError("redis down")
        self.written_ips.append((app_id, profile))

    async def get_device(self, app_id: int, fingerprint: str) -> DeviceProfile | None:
        return self.devices.get((app_id, fingerprint))

    async def set_device(self, app_id: int, profile: DeviceProfile) -> None:
        self.written_devices.append((app_id, profile))


def _service(ch: _FakeClickHouse, cache: _FakeCache, **kw) -> ReputationSyncService:
    return ReputationSyncService(
        clickhouse=ch,  # type: ignore[arg-type]
        profile_cache=cache,  # type: ignore[arg-type]
        **kw,
    )


# ---------- 分数契约 ----------
# 这张表必须与 tests/worker/test_reputation_writer.py 中的期望一致。
@pytest.mark.parametrize(
    ("total", "blocked", "expected"),
    [
        (100, 100, 0.0),  # 全拦截 → 0
        (100, 0, 100.0),  # 全放行 → 100
        (100, 50, 50.0),
        (0, 0, 50.0),  # 无样本 → 中性 50，不是 0
        (10, 20, 0.0),  # blocked > total（MV 竞态）截顶到 0
        (3, 1, 66.67),  # 两位小数
    ],
)
def test_calc_score_contract(total: int, blocked: int, expected: float) -> None:
    assert _calc_score(total, blocked) == expected


def test_zero_samples_is_neutral_not_hostile() -> None:
    """无样本必须是 50，返回 0 会让新 IP 被当成全拦截过的恶意 IP。"""
    assert _calc_score(0, 0) == 50.0


# ---------- IP 同步 ----------
@pytest.mark.asyncio
async def test_ip_written_with_score() -> None:
    ch = _FakeClickHouse(
        ip_rows=[{"app_id": 7, "ip": "203.0.113.7", "total": 100, "blocked": 25}]
    )
    cache = _FakeCache()

    result = await _service(ch, cache).sync()

    assert result.ips_written == 1
    app_id, written = cache.written_ips[0]
    assert app_id == 7
    assert written.ip == "203.0.113.7"
    assert written.reputation_score == 75.0
    assert written.reputation_samples == 100


@pytest.mark.asyncio
async def test_ip_reputation_is_per_tenant() -> None:
    """同一 IP 在不同租户下各写一条，互不影响。

    共享一条记录会让 A 站的爬虫流量压低 B 站对同一 IP 的评分——多租户隔离
    破损，且运营无法解释 B 站正常访客为何信誉分很低。
    """
    ch = _FakeClickHouse(
        ip_rows=[
            {"app_id": 1, "ip": "203.0.113.7", "total": 100, "blocked": 100},
            {"app_id": 2, "ip": "203.0.113.7", "total": 100, "blocked": 0},
        ]
    )
    cache = _FakeCache()

    await _service(ch, cache).sync()

    by_app = {app_id: profile.reputation_score for app_id, profile in cache.written_ips}
    assert by_app == {1: 0.0, 2: 100.0}


@pytest.mark.asyncio
async def test_existing_ip_profile_fields_preserved() -> None:
    """合并而非覆盖：MMDB 富化的国家/ASN 不能被声誉回写抹掉。"""
    ch = _FakeClickHouse(
        ip_rows=[{"app_id": 7, "ip": "203.0.113.7", "total": 50, "blocked": 0}]
    )
    cache = _FakeCache(
        ips={(7, "203.0.113.7"): IpProfile(ip="203.0.113.7", country="CN", asn=4134)}
    )

    await _service(ch, cache).sync()

    _, written = cache.written_ips[0]
    assert written.country == "CN"
    assert written.asn == 4134
    assert written.reputation_score == 100.0


@pytest.mark.asyncio
async def test_total_requests_never_regresses() -> None:
    """MV 只覆盖 lookback 窗口，取 max 避免把历史累计量改小。"""
    ch = _FakeClickHouse(
        ip_rows=[{"app_id": 7, "ip": "203.0.113.7", "total": 10, "blocked": 0}]
    )
    cache = _FakeCache(
        ips={(7, "203.0.113.7"): IpProfile(ip="203.0.113.7", totalRequests=9_000)}
    )

    await _service(ch, cache).sync()

    assert cache.written_ips[0][1].total_requests == 9_000


@pytest.mark.asyncio
async def test_last_seen_at_refreshed() -> None:
    ch = _FakeClickHouse(
        ip_rows=[{"app_id": 7, "ip": "203.0.113.7", "total": 10, "blocked": 0}]
    )
    old = datetime(2020, 1, 1, tzinfo=UTC)
    cache = _FakeCache(
        ips={(7, "203.0.113.7"): IpProfile(ip="203.0.113.7", lastSeenAt=old)}
    )

    await _service(ch, cache).sync()

    assert cache.written_ips[0][1].last_seen_at > old


# ---------- 设备同步 ----------
@pytest.mark.asyncio
async def test_device_written_with_app_scope() -> None:
    ch = _FakeClickHouse(
        device_rows=[{"app_id": 7, "fingerprint": "fp_abc", "total": 40, "blocked": 10}]
    )
    cache = _FakeCache()

    result = await _service(ch, cache).sync()

    assert result.devices_written == 1
    app_id, profile = cache.written_devices[0]
    assert app_id == 7
    assert profile.fingerprint == "fp_abc"
    assert profile.reputation_score == 75.0


@pytest.mark.asyncio
async def test_new_device_profile_has_last_seen_at() -> None:
    """新建画像必须带 last_seen_at，否则设备年龄类 scorer 拿不到基准时间。"""
    ch = _FakeClickHouse(
        device_rows=[{"app_id": 1, "fingerprint": "fp_new", "total": 10, "blocked": 0}]
    )
    cache = _FakeCache()

    await _service(ch, cache).sync()

    _, profile = cache.written_devices[0]
    assert profile.last_seen_at is not None


# ---------- fail-open ----------
@pytest.mark.asyncio
async def test_ip_query_failure_does_not_stop_device_sync() -> None:
    """两条子步骤相互独立：IP 侧 ClickHouse 故障不该让设备侧也不同步。"""
    ch = _FakeClickHouse(
        ip_fails=True,
        device_rows=[{"app_id": 1, "fingerprint": "fp_abc", "total": 10, "blocked": 0}],
    )
    cache = _FakeCache()

    result = await _service(ch, cache).sync()

    assert result.ips_written == 0
    assert result.devices_written == 1
    assert any("ip_query_failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_device_query_failure_does_not_stop_ip_sync() -> None:
    ch = _FakeClickHouse(
        device_fails=True,
        ip_rows=[{"app_id": 7, "ip": "203.0.113.7", "total": 10, "blocked": 0}],
    )
    cache = _FakeCache()

    result = await _service(ch, cache).sync()

    assert result.ips_written == 1
    assert any("device_query_failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_redis_write_failure_recorded_not_raised() -> None:
    """单条写失败只记错误继续下一条，不能让整次同步中断。"""
    ch = _FakeClickHouse(
        ip_rows=[
            {"app_id": 7, "ip": "203.0.113.7", "total": 10, "blocked": 0},
            {"app_id": 7, "ip": "203.0.113.8", "total": 10, "blocked": 0},
        ]
    )
    cache = _FakeCache(set_ip_fails=True)

    result = await _service(ch, cache).sync()

    assert result.ips_written == 0
    assert len(result.errors) == 2


@pytest.mark.asyncio
async def test_empty_result_writes_nothing() -> None:
    ch = _FakeClickHouse()
    cache = _FakeCache()

    result = await _service(ch, cache).sync()

    assert (result.ips_written, result.devices_written, result.errors) == (0, 0, [])


# ---------- 响应形状 ----------
@pytest.mark.asyncio
async def test_to_dict_caps_error_list() -> None:
    """错误列表回传上限 20 条，避免一次大范围故障撑爆响应体。"""
    ch = _FakeClickHouse(
        ip_rows=[
            {"app_id": 7, "ip": f"203.0.113.{i}", "total": 10, "blocked": 0}
            for i in range(1, 31)
        ]
    )
    cache = _FakeCache(set_ip_fails=True)

    payload = (await _service(ch, cache).sync()).to_dict()

    assert payload["error_count"] == 30
    assert len(payload["errors"]) == 20


@pytest.mark.asyncio
async def test_lookback_and_min_samples_passed_to_query() -> None:
    """参数必须真的进 SQL，否则改配置无效且没有任何报错。"""

    class _CapturingCH(_FakeClickHouse):
        def __init__(self) -> None:
            super().__init__()
            self.params: list[dict] = []

        async def fetch(self, sql: str, params: dict | None = None) -> list[dict]:
            self.params.append(params or {})
            return await super().fetch(sql, params)

    ch = _CapturingCH()
    await _service(ch, _FakeCache(), lookback_days=30, min_samples=99).sync()

    assert all(p["lookback_days"] == 30 for p in ch.params)
    assert all(p["min_samples"] == 99 for p in ch.params)

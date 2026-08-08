"""把聚合出的声誉分写回 Redis ProfileCache。

worker 的 ``ReputationWriter`` 与 admin 的 ``ReputationSyncService`` 都只是
本类的薄封装，保证两侧写出的画像逐字段一致。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from fangyu_shared.logging import get_logger
from fangyu_shared.reputation.aggregator import (
    IpReputationRow,
    fetch_device_reputation,
    fetch_ip_reputation,
)
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile

_logger = get_logger("shared.reputation_syncer")


class _Cache(Protocol):
    async def get_ip(self, site_id: int, ip: str) -> IpProfile | None: ...
    async def set_ip(self, site_id: int, profile: IpProfile) -> None: ...
    async def get_device(self, site_id: int, fingerprint: str) -> DeviceProfile | None: ...
    async def set_device(self, site_id: int, profile: DeviceProfile) -> None: ...


class _Fetcher(Protocol):
    async def fetch(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


IpRowsSink = Callable[[list[IpReputationRow]], Awaitable[int]]
"""IP 聚合结果的旁路消费者，返回它自己写出的条数。

用于 PROF → INTEL 回流：让调用方复用同一次聚合结果，不必为了拿同样的数据
再扫一遍 MV。异常由 :class:`ReputationSyncer` 兜住，不影响 Redis 写回。
"""


@dataclass(slots=True)
class ReputationSyncConfig:
    lookback_days: int = 7
    """向前追溯天数；覆盖更多历史让分数更稳定。"""
    min_samples: int = 5
    """最少样本数门槛；样本不足的 IP/指纹跳过，避免一次访问就压低信誉分。"""


@dataclass(slots=True)
class ReputationSyncOutcome:
    ips_written: int = 0
    devices_written: int = 0
    feedback_written: int = 0
    """旁路消费者（情报回流）写出的条数。"""
    errors: list[str] = field(default_factory=list)


class ReputationSyncer:
    """从 ClickHouse MV 拉取声誉聚合并写回 Redis ProfileCache。"""

    def __init__(
        self,
        *,
        clickhouse: _Fetcher,
        profile_cache: _Cache,
        config: ReputationSyncConfig | None = None,
        ip_rows_sink: IpRowsSink | None = None,
    ) -> None:
        self._ch = clickhouse
        self._cache = profile_cache
        self._cfg = config or ReputationSyncConfig()
        self._ip_rows_sink = ip_rows_sink

    async def run_once(self) -> ReputationSyncOutcome:
        """执行一次完整同步。

        fail-open 且 IP / 设备两条子步骤相互独立：一侧的 ClickHouse 故障不该
        让另一侧也不同步。两者顺序执行而非并发——并发时两条全量扫描会同时压
        在同一个 ClickHouse 连接池上，而这是个小时级的离线任务，没有抢延迟的
        必要。
        """
        outcome = ReputationSyncOutcome()
        await self._sync_ip(outcome)
        await self._sync_device(outcome)
        _logger.info(
            "reputation_sync_done",
            ips_written=outcome.ips_written,
            devices_written=outcome.devices_written,
            feedback_written=outcome.feedback_written,
            errors=len(outcome.errors),
        )
        return outcome

    # ------------------------------------------------------------------
    # IP 声誉
    # ------------------------------------------------------------------

    async def _sync_ip(self, outcome: ReputationSyncOutcome) -> None:
        try:
            rows = await fetch_ip_reputation(
                self._ch,
                lookback_days=self._cfg.lookback_days,
                min_samples=self._cfg.min_samples,
            )
        except Exception as exc:
            self._record(outcome, f"ip_query_failed: {exc}")
            return

        now = datetime.now(tz=UTC)
        for row in rows:
            try:
                await self._write_ip(row, now)
                outcome.ips_written += 1
            except Exception as exc:
                self._record(outcome, f"ip_write_failed site={row.app_id} ip={row.ip}: {exc}")

        await self._run_sink(rows, outcome)

    async def _write_ip(self, row: IpReputationRow, now: datetime) -> None:
        existing = await self._cache.get_ip(row.app_id, row.ip)
        # 这里不写 blocked_requests：``IpProfile`` 上没有这个字段（只有
        # ``DeviceProfile`` 有，供 DeviceScorer 的 high_block_rate 分支用），
        # 硬塞进 model_copy(update=...) 会绕过校验产生一个不在 schema 里的
        # 属性，序列化时被丢掉——写了等于没写，还留下「已经写了」的错觉。
        # IP 侧的拦截量由 reputation_score 表达：分数 = 100 - 拦截率×100。
        updates: dict[str, Any] = {
            "reputation_score": row.score,
            "reputation_samples": row.total,
            "last_seen_at": now,
        }
        if existing is not None:
            # total_requests 取 max：MV 只覆盖 lookback 窗口，直接赋值会把历史
            # 累计量改小。
            updates["total_requests"] = max(existing.total_requests, row.total)
            updated = existing.model_copy(update=updates)
        else:
            updated = IpProfile(ip=row.ip, total_requests=row.total, **updates)
        await self._cache.set_ip(row.app_id, updated)

    async def _run_sink(
        self, rows: list[IpReputationRow], outcome: ReputationSyncOutcome
    ) -> None:
        """执行旁路消费者。它的失败不能影响已经写好的 Redis 画像。"""
        if self._ip_rows_sink is None or not rows:
            return
        try:
            outcome.feedback_written = await self._ip_rows_sink(rows)
        except Exception as exc:
            self._record(outcome, f"ip_feedback_failed: {exc}")

    # ------------------------------------------------------------------
    # 设备指纹声誉
    # ------------------------------------------------------------------

    async def _sync_device(self, outcome: ReputationSyncOutcome) -> None:
        try:
            rows = await fetch_device_reputation(
                self._ch,
                lookback_days=self._cfg.lookback_days,
                min_samples=self._cfg.min_samples,
            )
        except Exception as exc:
            self._record(outcome, f"device_query_failed: {exc}")
            return

        now = datetime.now(tz=UTC)
        for row in rows:
            try:
                existing = await self._cache.get_device(row.app_id, row.fingerprint)
                updates: dict[str, Any] = {
                    "reputation_score": row.score,
                    "reputation_samples": row.total,
                    # 写入 blocked_requests 才能让 DeviceScorer 的
                    # high_block_rate 分支真正生效：此前没有任何代码写这个
                    # 字段，它恒为 0，那条分支永远不触发。
                    #
                    # 口径说明：blocked 取自 lookback 窗口，而 total_requests
                    # 取 max(历史, 窗口) 以保持单调不回退，两者分母并不严格
                    # 同源。窗口内流量下滑时分母偏大 → 算出的拦截率偏低 →
                    # 结论偏保守，只会漏放不会误杀，因此接受这个偏差。
                    "blocked_requests": row.blocked,
                    # last_seen_at 必须显式给：设备年龄类判定拿它当基准时间，
                    # 缺失时新建的画像看起来「从未出现过」。
                    "last_seen_at": now,
                }
                if existing is not None:
                    updates["total_requests"] = max(existing.total_requests, row.total)
                    updated = existing.model_copy(update=updates)
                else:
                    updated = DeviceProfile(
                        fingerprint=row.fingerprint, total_requests=row.total, **updates
                    )
                await self._cache.set_device(row.app_id, updated)
                outcome.devices_written += 1
            except Exception as exc:
                self._record(
                    outcome,
                    f"device_write_failed site={row.app_id} fp={row.fingerprint}: {exc}",
                )

    def _record(self, outcome: ReputationSyncOutcome, msg: str) -> None:
        outcome.errors.append(msg)
        _logger.warning(msg)

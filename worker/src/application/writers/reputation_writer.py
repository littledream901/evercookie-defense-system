"""Reputation 回流周期任务。

从 ClickHouse 物化视图读取过去 N 天的聚合数据，
计算 reputation_score = 100 - clamp(拦截率×100, 0, 100)，
通过 ProfileCache 写入 Redis，供 IpReputationScorer 使用。

只写样本量 >= min_samples 的记录，避免单次访问就压低信誉分。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fangyu_shared.cache.profile_cache import ProfileCache
from fangyu_shared.clickhouse_manager import ClickHouseClient
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile

_logger = get_logger("worker.reputation_writer")


@dataclass(slots=True)
class ReputationWriterConfig:
    lookback_days: int = 7
    """向前追溯天数；覆盖更多历史让分数更稳定。"""
    min_samples: int = 5
    """最少样本数门槛；样本不足的 IP/指纹跳过，避免误判。"""
    ip_ttl: int = 86_400
    """IP 画像在 Redis 中的 TTL（秒），默认 24 小时。"""
    device_ttl: int = 86_400
    """设备画像 TTL（秒）。"""


@dataclass(slots=True)
class ReputationSyncResult:
    ips_written: int = 0
    devices_written: int = 0
    errors: list[str] = field(default_factory=list)


class ReputationWriter:
    """按周期从 ClickHouse 拉取声誉聚合，回写 Redis ProfileCache。"""

    def __init__(
        self,
        *,
        clickhouse: ClickHouseClient,
        profile_cache: ProfileCache,
        config: ReputationWriterConfig | None = None,
    ) -> None:
        self._ch = clickhouse
        self._cache = profile_cache
        self._cfg = config or ReputationWriterConfig()

    async def run_once(self) -> ReputationSyncResult:
        """执行一次完整同步，返回写入统计。fail-open：任何子步骤失败不中断另一个。"""
        result = ReputationSyncResult()

        ip_task = asyncio.create_task(self._sync_ip_reputation(result))
        fp_task = asyncio.create_task(self._sync_device_reputation(result))
        await asyncio.gather(ip_task, fp_task, return_exceptions=True)

        _logger.info(
            "reputation_sync_done",
            ips_written=result.ips_written,
            devices_written=result.devices_written,
            errors=len(result.errors),
        )
        return result

    # ------------------------------------------------------------------
    # IP 声誉
    # ------------------------------------------------------------------

    async def _sync_ip_reputation(self, result: ReputationSyncResult) -> None:
        sql = """
            SELECT
                ip,
                sum(total_count)   AS total,
                sum(blocked_count) AS blocked
            FROM fangyu.mv_ip_reputation_daily
            WHERE log_date >= today() - {lookback_days}
              AND ip != ''
            GROUP BY ip
            HAVING total >= {min_samples}
        """
        try:
            rows = await self._ch.fetch(
                sql,
                params={
                    "lookback_days": self._cfg.lookback_days,
                    "min_samples": self._cfg.min_samples,
                },
            )
        except Exception as exc:
            msg = f"ip_reputation_query_failed: {exc}"
            result.errors.append(msg)
            _logger.warning(msg)
            return

        now = datetime.now(tz=UTC)

        for row in rows:
            ip: str = row["ip"]
            total: int = int(row["total"])
            blocked: int = int(row["blocked"])
            score = _calc_score(total, blocked)

            try:
                existing = await self._cache.get_ip(ip)
                if existing is not None:
                    updated = existing.model_copy(
                        update={
                            "reputation_score": score,
                            "reputation_samples": total,
                            "total_requests": max(existing.total_requests, total),
                            "last_seen_at": now,
                        }
                    )
                else:
                    updated = IpProfile(
                        ip=ip,
                        reputation_score=score,
                        reputation_samples=total,
                        total_requests=total,
                    )
                await self._cache.set_ip(updated)
                result.ips_written += 1
            except Exception as exc:
                msg = f"ip_write_failed ip={ip}: {exc}"
                result.errors.append(msg)
                _logger.warning(msg)

    # ------------------------------------------------------------------
    # 设备指纹声誉
    # ------------------------------------------------------------------

    async def _sync_device_reputation(self, result: ReputationSyncResult) -> None:
        sql = """
            SELECT
                app_id,
                fingerprint,
                sum(total_count)   AS total,
                sum(blocked_count) AS blocked
            FROM fangyu.mv_fingerprint_reputation_daily
            WHERE log_date >= today() - {lookback_days}
              AND fingerprint != ''
            GROUP BY app_id, fingerprint
            HAVING total >= {min_samples}
        """
        try:
            rows = await self._ch.fetch(
                sql,
                params={
                    "lookback_days": self._cfg.lookback_days,
                    "min_samples": self._cfg.min_samples,
                },
            )
        except Exception as exc:
            msg = f"device_reputation_query_failed: {exc}"
            result.errors.append(msg)
            _logger.warning(msg)
            return

        dev_cache = self._cache
        now = datetime.now(tz=UTC)

        for row in rows:
            app_id: int = int(row["app_id"])
            fingerprint: str = row["fingerprint"]
            total: int = int(row["total"])
            blocked: int = int(row["blocked"])
            score = _calc_score(total, blocked)

            try:
                existing = await dev_cache.get_device(app_id, fingerprint)
                if existing is not None:
                    updated = existing.model_copy(
                        update={
                            "reputation_score": score,
                            "reputation_samples": total,
                            "total_requests": max(existing.total_requests, total),
                            "last_seen_at": now,
                        }
                    )
                else:
                    # last_seen_at 必须显式给：设备年龄类判定拿它当基准时间，
                    # 缺失时新建的画像看起来「从未出现过」。admin 侧的
                    # ReputationSyncService 同样设置，两处不能不一致。
                    updated = DeviceProfile(
                        fingerprint=fingerprint,
                        reputation_score=score,
                        reputation_samples=total,
                        total_requests=total,
                        last_seen_at=now,
                    )
                await dev_cache.set_device(app_id, updated)
                result.devices_written += 1
            except Exception as exc:
                msg = f"device_write_failed app={app_id} fp={fingerprint}: {exc}"
                result.errors.append(msg)
                _logger.warning(msg)


def _calc_score(total: int, blocked: int) -> float:
    """reputation_score = 100 - clamp(拦截率×100, 0, 100)。

    拦截率越高→信誉越低；全放行=100分；全拦截=0分。
    结果保留两位小数以减少 JSON 体积。
    """
    if total <= 0:
        return 50.0
    rate = min(1.0, max(0.0, blocked / total))
    return round(100.0 - rate * 100.0, 2)

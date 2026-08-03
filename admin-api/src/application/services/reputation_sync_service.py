"""声誉回流手动同步服务（admin-api 侧）。

与 worker.reputation_writer 逻辑相同，供管理员通过 HTTP 手动触发。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fangyu_shared.cache.profile_cache import ProfileCache
from fangyu_shared.clickhouse_manager import ClickHouseClient
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile

_logger = get_logger("admin.reputation_sync")


@dataclass(slots=True)
class ReputationSyncResult:
    ips_written: int = 0
    devices_written: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ips_written": self.ips_written,
            "devices_written": self.devices_written,
            "error_count": len(self.errors),
            "errors": self.errors[:20],  # 最多回传 20 条错误摘要，防止响应过大
        }


class ReputationSyncService:
    """从 ClickHouse MV 拉取声誉聚合并写回 Redis ProfileCache。"""

    def __init__(
        self,
        *,
        clickhouse: ClickHouseClient,
        profile_cache: ProfileCache,
        lookback_days: int = 7,
        min_samples: int = 5,
    ) -> None:
        self._ch = clickhouse
        self._cache = profile_cache
        self._lookback_days = lookback_days
        self._min_samples = min_samples

    async def sync(self) -> ReputationSyncResult:
        """执行一次完整的声誉同步。fail-open：IP / 设备子步骤相互独立。"""
        result = ReputationSyncResult()
        await asyncio.gather(
            self._sync_ip(result),
            self._sync_device(result),
            return_exceptions=True,
        )
        _logger.info(
            "admin_reputation_sync_done",
            ips=result.ips_written,
            devices=result.devices_written,
            errors=len(result.errors),
        )
        return result

    # ------------------------------------------------------------------

    async def _sync_ip(self, result: ReputationSyncResult) -> None:
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
                params={"lookback_days": self._lookback_days, "min_samples": self._min_samples},
            )
        except Exception as exc:
            msg = f"ip_query_failed: {exc}"
            result.errors.append(msg)
            _logger.warning(msg)
            return

        now = datetime.now(tz=timezone.utc)
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

    async def _sync_device(self, result: ReputationSyncResult) -> None:
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
                params={"lookback_days": self._lookback_days, "min_samples": self._min_samples},
            )
        except Exception as exc:
            msg = f"device_query_failed: {exc}"
            result.errors.append(msg)
            _logger.warning(msg)
            return

        now = datetime.now(tz=timezone.utc)
        for row in rows:
            app_id: int = int(row["app_id"])
            fingerprint: str = row["fingerprint"]
            total: int = int(row["total"])
            blocked: int = int(row["blocked"])
            score = _calc_score(total, blocked)
            try:
                existing = await self._cache.get_device(app_id, fingerprint)
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
                    updated = DeviceProfile(
                        fingerprint=fingerprint,
                        reputation_score=score,
                        reputation_samples=total,
                        total_requests=total,
                        last_seen_at=now,
                    )
                await self._cache.set_device(app_id, updated)
                result.devices_written += 1
            except Exception as exc:
                msg = f"device_write_failed app={app_id} fp={fingerprint}: {exc}"
                result.errors.append(msg)
                _logger.warning(msg)


def _calc_score(total: int, blocked: int) -> float:
    if total <= 0:
        return 50.0
    rate = min(1.0, max(0.0, blocked / total))
    return round(100.0 - rate * 100.0, 2)

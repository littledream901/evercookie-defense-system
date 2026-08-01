"""频控阈值与封禁的编排服务。

写入顺序统一为「先落库 commit、再同步 Redis」，与 threat_intel 一致。这个
顺序的取舍：Redis 写失败时 DB 已有记录，下次启动引导或手工重新同步可以自愈；
反过来先写 Redis 则可能出现「网关已生效但库里查不到」的幽灵配置。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.schemas.clock import ClockLimits, default_limits
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.clock_sync import ClockSync
from src.infrastructure.repositories.clock_limits_repository import (
    ClockLimitsRepository,
)


class ClockService:
    def __init__(self, session: AsyncSession, sync: ClockSync) -> None:
        self._repo = ClockLimitsRepository(session)
        self._session = session
        self._sync = sync

    # ---------- 阈值 ----------
    async def get_limits(self, app_id: int) -> ClockLimits:
        """读取阈值。未配置时返回默认值，与 gateway 的回退行为保持一致。"""
        row = await self._repo.get(app_id)
        if row is None:
            return default_limits(app_id)
        return self._to_limits(row)

    async def put_limits(
        self,
        app_id: int,
        *,
        enabled: bool,
        windows: dict[str, int],
        ban_seconds: int,
        ban_enabled: bool,
    ) -> ClockLimits:
        """更新阈值并同步 Redis。

        先构造 ``ClockLimits`` 走一遍校验，再落库——这样未知窗口名、负阈值、
        超上限的封禁时长会在写库前就被拒绝，不会留下网关读不了的脏配置。
        """
        limits = ClockLimits(
            appId=app_id,
            enabled=enabled,
            windows=windows,
            banSeconds=ban_seconds,
            banEnabled=ban_enabled,
        )
        await self._repo.upsert(
            app_id,
            enabled=limits.enabled,
            windows=limits.windows,
            ban_seconds=limits.ban_seconds,
            ban_enabled=limits.ban_enabled,
        )
        await self._session.commit()
        await self._sync.put_limits(limits)
        return limits

    async def reset_limits(self, app_id: int) -> bool:
        """删除站点自定义阈值，回退到默认值。"""
        deleted = await self._repo.delete(app_id)
        await self._session.commit()
        await self._sync.delete_limits(app_id)
        return deleted

    async def resync_all(self) -> dict[str, int]:
        """把库里全部阈值重新推到 Redis。

        用于 Redis flush 后的恢复，以及启动引导。
        """
        rows = await self._repo.list_all()
        for row in rows:
            await self._sync.put_limits(self._to_limits(row))
        return {"synced": len(rows)}

    # ---------- 封禁 ----------
    async def ban(
        self,
        app_id: int,
        dimension: ClockDimension,
        value: str,
        *,
        seconds: int,
        reason: str,
    ) -> dict[str, Any]:
        await self._sync.ban(
            app_id, dimension, value, seconds=seconds, reason=reason
        )
        return {
            "appId": app_id,
            "dimension": dimension.value,
            "value": value,
            "ttlSeconds": seconds,
            "reason": reason,
        }

    async def unban(
        self, app_id: int, dimension: ClockDimension, value: str
    ) -> bool:
        return await self._sync.unban(app_id, dimension, value)

    async def get_ban(
        self, app_id: int, dimension: ClockDimension, value: str
    ) -> dict[str, Any] | None:
        return await self._sync.get_ban(app_id, dimension, value)

    @staticmethod
    def _to_limits(row: Any) -> ClockLimits:
        return ClockLimits(
            appId=row.app_id,
            enabled=row.enabled,
            windows=dict(row.windows or {}),
            banSeconds=row.ban_seconds,
            banEnabled=row.ban_enabled,
        )

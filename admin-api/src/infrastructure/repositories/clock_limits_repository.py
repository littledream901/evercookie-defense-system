"""频控阈值仓储：MySQL CRUD。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import ClockLimitsModel


class ClockLimitsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        app_id: int,
        *,
        enabled: bool,
        windows: dict[str, int],
        ban_seconds: int,
        ban_enabled: bool,
    ) -> ClockLimitsModel:
        stmt = (
            mysql_insert(ClockLimitsModel)
            .values(
                app_id=app_id,
                enabled=enabled,
                windows=windows,
                ban_seconds=ban_seconds,
                ban_enabled=ban_enabled,
            )
            .on_duplicate_key_update(
                enabled=enabled,
                windows=windows,
                ban_seconds=ban_seconds,
                ban_enabled=ban_enabled,
                updated_at=func.now(),
            )
        )
        await self._session.execute(stmt)
        row = await self.get(app_id)
        return row  # type: ignore[return-value]

    async def get(self, app_id: int) -> ClockLimitsModel | None:
        return await self._session.scalar(
            select(ClockLimitsModel).where(ClockLimitsModel.app_id == app_id)
        )

    async def delete(self, app_id: int) -> bool:
        row = await self.get(app_id)
        if row is None:
            return False
        await self._session.delete(row)
        return True

    async def list_all(self) -> list[ClockLimitsModel]:
        """全量读取，供启动时重建 Redis。"""
        rows = await self._session.scalars(select(ClockLimitsModel))
        return list(rows.all())

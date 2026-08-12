"""默认处置仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import DefaultDispositionModel


class DefaultDispositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_site(self, site_id: int) -> DefaultDispositionModel | None:
        stmt = (
            select(DefaultDispositionModel)
            .where(DefaultDispositionModel.site_id == site_id)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        site_id: int,
        *,
        disposition: dict,
    ) -> DefaultDispositionModel:
        """PUT 语义：不存在则创建，存在则全量覆盖。"""
        stmt = (
            mysql_insert(DefaultDispositionModel)
            .values(site_id=site_id, disposition=disposition)
            .on_duplicate_key_update(disposition=disposition)
        )
        await self._session.execute(stmt)
        await self._session.flush()
        row = await self.get_by_site(site_id)
        return row  # type: ignore[return-value]

    async def reset(self, site_id: int) -> bool:
        """删除配置，让站点回退到全局/系统默认。"""
        row = await self.get_by_site(site_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

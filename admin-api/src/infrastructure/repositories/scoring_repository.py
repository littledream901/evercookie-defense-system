"""评分配置仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import ScoringConfigModel


class ScoringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_app(self, site_id: int) -> ScoringConfigModel | None:
        stmt = (
            select(ScoringConfigModel)
            .where(ScoringConfigModel.site_id == site_id)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        site_id: int,
        *,
        name: str = "",
        enabled: bool = True,
        threshold_suspect: int = 40,
        threshold_hostile: int = 70,
        weights: dict,
        disposition_suspect: dict | None = None,
        disposition_hostile: dict | None = None,
    ) -> ScoringConfigModel:
        """PUT 语义：不存在则创建，存在则全量覆盖。"""
        stmt = (
            mysql_insert(ScoringConfigModel)
            .values(
                site_id=site_id,
                name=name,
                enabled=enabled,
                threshold_suspect=threshold_suspect,
                threshold_hostile=threshold_hostile,
                weights=weights,
                disposition_suspect=disposition_suspect,
                disposition_hostile=disposition_hostile,
            )
            .on_duplicate_key_update(
                name=name,
                enabled=enabled,
                threshold_suspect=threshold_suspect,
                threshold_hostile=threshold_hostile,
                weights=weights,
                disposition_suspect=disposition_suspect,
                disposition_hostile=disposition_hostile,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        row = await self.get_by_app(site_id)
        return row  # type: ignore[return-value]

    async def reset(self, site_id: int) -> bool:
        """删除配置，让站点回退到全局默认。"""
        row = await self.get_by_app(site_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def list_all(self) -> list[ScoringConfigModel]:
        """全量扫描，供启动 bootstrap 使用，记录量级与站点数相同，不分页。"""
        stmt = select(ScoringConfigModel)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

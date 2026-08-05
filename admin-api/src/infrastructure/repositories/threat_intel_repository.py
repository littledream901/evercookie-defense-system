"""威胁情报仓储：MySQL CRUD + 分页查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fangyu_shared.utils.time import utcnow
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import ThreatIntelModel


class ThreatIntelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        ip: str,
        *,
        category: str = "malicious",
        severity: str = "medium",
        source: str = "manual",
        confidence: int = 80,
        description: str = "",
        expires_at: datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ThreatIntelModel:
        stmt = (
            mysql_insert(ThreatIntelModel)
            .values(
                ip=ip,
                category=category,
                severity=severity,
                source=source,
                confidence=confidence,
                description=description,
                is_active=True,
                expires_at=expires_at,
                extra=extra,
            )
            .on_duplicate_key_update(
                category=category,
                severity=severity,
                source=source,
                confidence=confidence,
                description=description,
                is_active=True,
                expires_at=expires_at,
                extra=extra,
                updated_at=func.now(),
            )
        )
        await self._session.execute(stmt)
        row = await self._session.scalar(
            select(ThreatIntelModel).where(ThreatIntelModel.ip == ip)
        )
        return row  # type: ignore[return-value]

    async def deactivate(self, ip: str) -> bool:
        result = await self._session.execute(
            update(ThreatIntelModel)
            .where(ThreatIntelModel.ip == ip)
            .values(is_active=False)
        )
        return result.rowcount > 0

    async def get(self, ip: str) -> ThreatIntelModel | None:
        return await self._session.scalar(
            select(ThreatIntelModel).where(ThreatIntelModel.ip == ip)
        )

    async def list_active(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
        severity: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[ThreatIntelModel], int]:
        now = utcnow()
        base_where = and_(
            ThreatIntelModel.is_active == True,
            (ThreatIntelModel.expires_at == None) | (ThreatIntelModel.expires_at > now),
        )
        if category:
            base_where = and_(base_where, ThreatIntelModel.category == category)
        if source:
            base_where = and_(base_where, ThreatIntelModel.source == source)
        if severity:
            base_where = and_(base_where, ThreatIntelModel.severity == severity)

        total = await self._session.scalar(
            select(func.count()).select_from(ThreatIntelModel).where(base_where)
        ) or 0

        rows = (
            await self._session.scalars(
                select(ThreatIntelModel)
                .where(base_where)
                .order_by(ThreatIntelModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return list(rows), int(total)

    async def count_by_source(self) -> dict[str, int]:
        """按 source 分组统计活跃条目数。

        口径与 :meth:`list_active` 一致（排除已过期条目），使前端卡片显示的
        条数与列表实际可见条数对得上。
        """
        now = utcnow()
        rows = await self._session.execute(
            select(ThreatIntelModel.source, func.count())
            .where(
                ThreatIntelModel.is_active == True,
                (ThreatIntelModel.expires_at == None) | (ThreatIntelModel.expires_at > now),
            )
            .group_by(ThreatIntelModel.source)
        )
        return {source: int(count) for source, count in rows.all()}

    async def list_all_active_ips(self) -> list[str]:
        now = utcnow()
        rows = await self._session.scalars(
            select(ThreatIntelModel.ip).where(
                ThreatIntelModel.is_active == True,
                (ThreatIntelModel.expires_at == None) | (ThreatIntelModel.expires_at > now),
            )
        )
        return list(rows.all())

    async def bulk_insert(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        for rec in records:
            stmt = (
                mysql_insert(ThreatIntelModel)
                .values(**rec)
                .on_duplicate_key_update(
                    category=rec.get("category", "malicious"),
                    severity=rec.get("severity", "medium"),
                    source=rec.get("source", "import"),
                    confidence=rec.get("confidence", 80),
                    is_active=True,
                    updated_at=func.now(),
                )
            )
            await self._session.execute(stmt)
        return len(records)

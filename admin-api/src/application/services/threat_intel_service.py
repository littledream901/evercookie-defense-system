"""威胁情报应用服务：协调 DB 仓储 + Redis 同步层。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.threat_intel_repository import ThreatIntelRepository
from src.infrastructure.threat_intel_sync import ThreatIntelSync


class ThreatIntelService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ThreatIntelRepository(session)
        self._session = session

    async def add(
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
    ) -> dict[str, Any]:
        record = await self._repo.upsert(
            ip,
            category=category,
            severity=severity,
            source=source,
            confidence=confidence,
            description=description,
            expires_at=expires_at,
            extra=extra,
        )
        await self._session.commit()
        await ThreatIntelSync.add(ip, category)
        return self._to_dict(record)

    async def remove(self, ip: str) -> bool:
        record = await self._repo.get(ip)
        category = record.category if record else "malicious"
        deactivated = await self._repo.deactivate(ip)
        await self._session.commit()
        if deactivated:
            await ThreatIntelSync.remove(ip, category)
        return deactivated

    async def list_active(
        self,
        *,
        category: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        rows, total = await self._repo.list_active(
            category=category, source=source, page=page, page_size=page_size
        )
        return {
            "items": [self._to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def bulk_import(self, records: list[dict[str, Any]]) -> dict[str, int]:
        count = await self._repo.bulk_insert(records)
        await self._session.commit()
        await self.sync_to_redis()
        return {"imported": count}

    async def sync_to_redis(self) -> dict[str, Any]:
        all_ips = await self._repo.list_all_active_ips()
        rows, _ = await self._repo.list_active(page=1, page_size=100_000)
        ip_by_category: dict[str, list[str]] = {}
        for r in rows:
            ip_by_category.setdefault(r.category, []).append(r.ip)
        await ThreatIntelSync.full_sync(ip_by_category)
        stats = await ThreatIntelSync.stats()
        stats["synced_ips"] = len(all_ips)
        return stats

    async def redis_stats(self) -> dict[str, Any]:
        return await ThreatIntelSync.stats()

    @staticmethod
    def _to_dict(r: Any) -> dict[str, Any]:
        return {
            "id": r.id,
            "ip": r.ip,
            "category": r.category,
            "severity": r.severity,
            "source": r.source,
            "confidence": r.confidence,
            "description": r.description,
            "is_active": r.is_active,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "extra": r.extra,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

"""情报服务层。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.intel_sync import IntelSync
from src.infrastructure.repositories.intel_repository import IntelRepository, IntelType


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        c.name: getattr(row, c.name)
        for c in row.__table__.columns  # type: ignore[attr-defined]
    }


class IntelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IntelRepository(session)

    async def list(
        self,
        intel_type: IntelType,
        *,
        keyword: str | None = None,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = await self._repo.list_active(
            intel_type, keyword=keyword, filters=filters, page=page, page_size=page_size
        )
        return [_row_to_dict(r) for r in rows], total

    async def create(self, intel_type: IntelType, data: dict[str, Any]) -> dict[str, Any]:
        row = await self._repo.create(intel_type, data)
        result = _row_to_dict(row)
        await self._resync(intel_type)
        return result

    async def update(
        self, intel_type: IntelType, row_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = await self._repo.update(intel_type, row_id, data)
        if row is None:
            return None
        result = _row_to_dict(row)
        await self._resync(intel_type)
        return result

    async def delete(self, intel_type: IntelType, row_id: int) -> bool:
        ok = await self._repo.delete(intel_type, row_id)
        if ok:
            await self._resync(intel_type)
        return ok

    async def bulk_import(
        self, intel_type: IntelType, records: list[dict[str, Any]]
    ) -> dict[str, int]:
        imported, skipped = await self._repo.bulk_create(intel_type, records)
        if imported:
            await self._resync(intel_type)
        return {"imported": imported, "skipped": skipped}

    async def count(self, intel_type: IntelType) -> int:
        return await self._repo.count(intel_type)

    async def count_by_note_prefix(
        self, intel_type: IntelType, prefixes: list[str]
    ) -> dict[str, int]:
        return await self._repo.count_by_note_prefix(intel_type, prefixes)

    async def _resync(self, intel_type: IntelType) -> None:
        """写操作后把该类型全量重推 Redis，让 gateway 立即生效。

        单类型体量小（千级），全量覆盖比维护增量差异更简单可靠。
        先提交事务再推送，避免 DB 回滚后 Redis 残留未落库的数据。
        """
        await self._session.commit()
        rows = await self.get_all_active(intel_type)
        await IntelSync.full_sync(intel_type.value, rows)

    async def get_all_active(self, intel_type: IntelType) -> list[dict[str, Any]]:
        rows = await self._repo.get_all_active(intel_type)
        return [_row_to_dict(r) for r in rows]

    async def overview(self) -> dict[str, Any]:
        """汇总各类型条目数，供 overview 卡片展示。"""
        counts: dict[str, int] = {}
        total = 0
        for t in IntelType:
            c = await self._repo.count(t)
            counts[t.value] = c
            total += c
        return {
            "total_entries": total,
            "profile_field_count": counts.get("ip_profile", 0) + counts.get("asn_profile", 0),
            "last_sync_time": await IntelSync.last_sync_time(),
            "counts": counts,
        }

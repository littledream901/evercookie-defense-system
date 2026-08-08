"""规则组仓储（Admin 端）。"""

from __future__ import annotations

from fangyu_shared.schemas.disposition import Disposition
from fangyu_shared.schemas.rule import GroupMode, RuleGroup, RulePriority
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import RuleGroupModel


class RuleGroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, group_id: int) -> RuleGroup | None:
        row = await self._session.get(RuleGroupModel, group_id)
        if row is None:
            return None
        return self._to_domain(row)

    async def list_by_site(self, site_id: int) -> list[RuleGroup]:
        """查询某站点的所有规则组。"""
        stmt = select(RuleGroupModel).where(RuleGroupModel.site_id == site_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_domain(row) for row in rows]

    async def create(self, site_id: int, name: str, mode: GroupMode, priority: RulePriority, enabled: bool, on_no_match: Disposition | None) -> RuleGroup:
        """创建规则组。"""
        model = RuleGroupModel(
            site_id=site_id,
            name=name,
            mode=mode.value,
            priority=priority.value,
            enabled=enabled,
            on_no_match=on_no_match.model_dump(by_alias=True, mode="json") if on_no_match else None,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def update(self, group_id: int, name: str | None = None, mode: GroupMode | None = None, priority: RulePriority | None = None, enabled: bool | None = None, on_no_match: Disposition | None = None) -> RuleGroup | None:
        """更新规则组。"""
        row = await self._session.get(RuleGroupModel, group_id)
        if row is None:
            return None
        
        if name is not None:
            row.name = name
        if mode is not None:
            row.mode = mode.value
        if priority is not None:
            row.priority = priority.value
        if enabled is not None:
            row.enabled = enabled
        if on_no_match is not None:
            row.on_no_match = on_no_match.model_dump(by_alias=True, mode="json")
        
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_domain(row)

    async def delete(self, group_id: int) -> bool:
        """删除规则组。"""
        stmt = delete(RuleGroupModel).where(RuleGroupModel.id == group_id)
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[no-any-return]

    @staticmethod
    def _to_domain(row: RuleGroupModel) -> RuleGroup:
        return RuleGroup(
            id=row.id,
            site_id=row.site_id,
            name=row.name,
            mode=GroupMode(row.mode),
            priority=RulePriority(row.priority),
            enabled=row.enabled,
            on_no_match=Disposition.model_validate(row.on_no_match) if row.on_no_match else None,
        )

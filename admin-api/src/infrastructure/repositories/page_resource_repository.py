"""页面资源仓储。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.page_resource.entities import PageResource, PageResourceKind
from src.infrastructure.repositories.models import PageResourceModel


class PageResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, resource_id: int) -> PageResource | None:
        row = await self._session.get(PageResourceModel, resource_id)
        return self._to_domain(row) if row else None

    async def get_by_name(self, app_id: int, name: str) -> PageResource | None:
        stmt = (
            select(PageResourceModel)
            .where(PageResourceModel.app_id == app_id)
            .where(PageResourceModel.name == name)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_app(
        self,
        app_id: int,
        *,
        kind: PageResourceKind | None = None,
        enabled: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PageResource], int]:
        base = select(PageResourceModel).where(PageResourceModel.app_id == app_id)
        if kind is not None:
            base = base.where(PageResourceModel.kind == kind.value)
        if enabled is not None:
            base = base.where(PageResourceModel.enabled == enabled)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(PageResourceModel.updated_at.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()

        return [self._to_domain(r) for r in rows], int(total)

    async def create(self, resource: PageResource) -> PageResource:
        model = PageResourceModel(
            app_id=resource.app_id,
            name=resource.name,
            kind=resource.kind.value,
            content=resource.content,
            content_type=resource.content_type,
            enabled=resource.enabled,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def update(self, resource: PageResource) -> PageResource:
        assert resource.id is not None
        model = await self._session.get(PageResourceModel, resource.id)
        if model is None:
            raise LookupError(f"page_resource {resource.id} not found")
        model.name = resource.name
        model.kind = resource.kind.value
        model.content = resource.content
        model.content_type = resource.content_type
        model.enabled = resource.enabled
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def delete(self, resource_id: int) -> bool:
        model = await self._session.get(PageResourceModel, resource_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_domain(row: PageResourceModel) -> PageResource:
        return PageResource(
            id=row.id,
            app_id=row.app_id,
            name=row.name,
            kind=PageResourceKind(row.kind),
            content=row.content,
            content_type=row.content_type,
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

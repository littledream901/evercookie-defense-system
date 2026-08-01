"""应用（App）仓储。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.app.entities import Application, ApplicationStatus
from src.infrastructure.repositories.models import ApplicationModel


class AppRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, app_id: int) -> Application | None:
        row = await self._session.get(ApplicationModel, app_id)
        return self._to_domain(row) if row else None

    async def get_by_api_key(self, api_key: str) -> Application | None:
        stmt = select(ApplicationModel).where(ApplicationModel.api_key == api_key).limit(1)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_active_key_bindings(self) -> list[tuple[str, int]]:
        """启动引导：仅拉 (api_key, id) 二元组，用于全量刷新 Redis 映射。"""
        stmt = select(ApplicationModel.api_key, ApplicationModel.id).where(
            ApplicationModel.status == ApplicationStatus.ACTIVE.value
        )
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows if row[0] and row[1]]

    async def list_by_owner(self, owner_id: int) -> list[Application]:
        stmt = select(ApplicationModel).where(ApplicationModel.owner_user_id == owner_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [a for a in (self._to_domain(r) for r in rows) if a is not None]

    async def list_paged(
        self,
        *,
        keyword: str | None = None,
        status: ApplicationStatus | None = None,
        owner_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Application], int]:
        base = select(ApplicationModel)
        if keyword:
            like = f"%{keyword}%"
            base = base.where(ApplicationModel.name.ilike(like))
        if status is not None:
            base = base.where(ApplicationModel.status == status.value)
        if owner_id is not None:
            base = base.where(ApplicationModel.owner_user_id == owner_id)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(ApplicationModel.id.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        items = [a for a in (self._to_domain(r) for r in rows) if a is not None]
        return items, int(total)

    async def create(self, app: Application) -> Application:
        model = ApplicationModel(
            name=app.name,
            api_key=app.api_key,
            owner_user_id=app.owner_user_id,
            status=app.status.value,
            description=app.description,
            domains=app.domains,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)  # type: ignore[return-value]

    async def update(
        self,
        app_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        domains: list[str] | None = None,
        status: ApplicationStatus | None = None,
    ) -> Application | None:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return None
        if name is not None:
            model.name = name
        if description is not None:
            model.description = description
        if domains is not None:
            model.domains = domains
        if status is not None:
            model.status = status.value
        await self._session.flush()
        return self._to_domain(model)

    async def rotate_api_key(self, app_id: int, new_key: str) -> Application | None:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return None
        model.api_key = new_key
        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, app_id: int) -> bool:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_domain(row: ApplicationModel | None) -> Application | None:
        if row is None:
            return None
        return Application(
            id=row.id,
            name=row.name,
            api_key=row.api_key,
            owner_user_id=row.owner_user_id,
            status=ApplicationStatus(row.status),
            description=row.description,
            domains=list(row.domains or []),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

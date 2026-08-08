"""应用（Application）仓储 - V3 两层架构。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import ApplicationModel, SiteModel


def _gen_app_key() -> str:
    """生成应用标识，格式 app_<hex8>。"""
    return f"app_{uuid.uuid4().hex[:8]}"


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, app_id: int) -> ApplicationModel | None:
        return await self._session.get(ApplicationModel, app_id)

    async def get_by_app_key(self, app_key: str) -> ApplicationModel | None:
        stmt = select(ApplicationModel).where(ApplicationModel.app_key == app_key).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_owner(self, owner_id: int) -> list[ApplicationModel]:
        stmt = select(ApplicationModel).where(ApplicationModel.owner_user_id == owner_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_names(self, app_ids: list[int]) -> dict[int, str]:
        """批量取应用名，供站点列表回填 app_name，避免逐条查询。"""
        if not app_ids:
            return {}
        stmt = select(ApplicationModel.id, ApplicationModel.name).where(
            ApplicationModel.id.in_(app_ids)
        )
        rows = (await self._session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def list_active_bindings(self) -> list[tuple[str, int, str]]:
        """启动引导：拉 (app_key, id, app_secret)，用于全量刷新 Redis 映射。"""
        stmt = select(
            ApplicationModel.app_key,
            ApplicationModel.id,
            ApplicationModel.app_secret,
        ).where(ApplicationModel.is_active.is_(True))
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1], row[2] or "") for row in rows if row[0] and row[1]]

    async def list_paged(
        self,
        *,
        keyword: str | None = None,
        is_active: bool | None = None,
        owner_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ApplicationModel], int]:
        base = select(ApplicationModel)
        if keyword:
            like = f"%{keyword}%"
            base = base.where(
                or_(
                    ApplicationModel.name.ilike(like),
                    ApplicationModel.app_key.ilike(like),
                    ApplicationModel.description.ilike(like),
                )
            )
        if is_active is not None:
            base = base.where(ApplicationModel.is_active.is_(is_active))
        if owner_id is not None:
            base = base.where(ApplicationModel.owner_user_id == owner_id)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(ApplicationModel.id.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total)

    async def create(
        self,
        *,
        app_key: str | None = None,
        name: str,
        description: str = "",
        owner_user_id: int | None = None,
        app_secret: str,
        is_active: bool = True,
    ) -> ApplicationModel:
        model = ApplicationModel(
            app_key=app_key or _gen_app_key(),
            name=name,
            description=description,
            owner_user_id=owner_user_id,
            app_secret=app_secret,
            is_active=is_active,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(
        self,
        app_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> ApplicationModel | None:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return None
        if name is not None:
            model.name = name
        if description is not None:
            model.description = description
        if is_active is not None:
            model.is_active = is_active
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def rotate_secret(self, app_id: int, app_secret: str) -> ApplicationModel | None:
        """轮换应用密钥。"""
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return None
        model.app_secret = app_secret
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, app_id: int) -> bool:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def count_sites(self, app_id: int) -> int:
        """统计应用下的站点数量。"""
        stmt = select(func.count()).select_from(SiteModel).where(SiteModel.app_id == app_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def count_sites_batch(self, app_ids: list[int]) -> dict[int, int]:
        """批量统计站点数，供应用列表使用，避免逐条查询。"""
        if not app_ids:
            return {}
        stmt = (
            select(SiteModel.app_id, func.count())
            .where(SiteModel.app_id.in_(app_ids))
            .group_by(SiteModel.app_id)
        )
        rows = (await self._session.execute(stmt)).all()
        counts = {aid: 0 for aid in app_ids}
        for app_id, count in rows:
            counts[app_id] = count
        return counts

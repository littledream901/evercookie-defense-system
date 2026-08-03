"""应用（App）仓储。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.app.entities import Application
from src.infrastructure.repositories.models import ApplicationModel, RuleSiteModel, RuleModel


def _gen_site_id() -> str:
    """生成站点标识，格式 site_<hex8>，同时作为 X-App-Key 使用。"""
    return f"site_{uuid.uuid4().hex[:8]}"


class AppRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, app_id: int) -> Application | None:
        row = await self._session.get(ApplicationModel, app_id)
        return self._to_domain(row) if row else None

    async def get_by_site_id(self, site_id: str) -> Application | None:
        stmt = select(ApplicationModel).where(ApplicationModel.site_id == site_id).limit(1)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_app_id(self, app_id: str) -> Application | None:
        """兼容旧调用；新代码请使用 get_by_site_id。"""
        return await self.get_by_site_id(app_id)

    async def list_by_owner(self, owner_id: int) -> list[Application]:
        stmt = select(ApplicationModel).where(ApplicationModel.owner_user_id == owner_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [app for row in rows if (app := self._to_domain(row)) is not None]

    async def list_active_app_bindings(self) -> list[tuple[str, int, str]]:
        """启动引导：拉 (site_id, id, app_secret)，用于全量刷新 Redis 映射。"""
        stmt = select(
            ApplicationModel.site_id,
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
        access_mode: str | None = None,
        owner_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Application], int]:
        base = select(ApplicationModel)
        if keyword:
            like = f"%{keyword}%"
            base = base.where(
                or_(
                    ApplicationModel.name.ilike(like),
                    ApplicationModel.domain.ilike(like),
                    ApplicationModel.site_id.ilike(like),
                )
            )
        if is_active is not None:
            base = base.where(ApplicationModel.is_active.is_(is_active))
        if access_mode is not None:
            base = base.where(ApplicationModel.access_mode == access_mode)
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
            site_id=app.site_id or _gen_site_id(),
            name=app.name,
            domain=app.domain,
            alt_domains=app.alt_domains,
            access_mode=app.access_mode,
            app_secret=app.app_secret,
            sdk_version=app.sdk_version,
            gateway_url=app.gateway_url,
            is_active=app.is_active,
            owner_user_id=app.owner_user_id,
            clock_stats_enabled=app.clock_stats_enabled,
            log_retention_days=app.log_retention_days,
            remark=app.remark,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)  # type: ignore[return-value]

    async def update(
        self,
        app_id: int,
        *,
        name: str | None = None,
        alt_domains: list[str] | None = None,
        access_mode: str | None = None,
        sdk_version: str | None = None,
        gateway_url: str | None = None,
        is_active: bool | None = None,
        clock_stats_enabled: bool | None = None,
        log_retention_days: int | None = None,
        remark: str | None = None,
    ) -> Application | None:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return None
        if name is not None:
            model.name = name
        if alt_domains is not None:
            model.alt_domains = alt_domains
        if access_mode is not None:
            model.access_mode = access_mode
        if sdk_version is not None:
            model.sdk_version = sdk_version
        if gateway_url is not None:
            model.gateway_url = gateway_url
        if is_active is not None:
            model.is_active = is_active
        if clock_stats_enabled is not None:
            model.clock_stats_enabled = clock_stats_enabled
        if log_retention_days is not None:
            model.log_retention_days = log_retention_days
        if remark is not None:
            model.remark = remark
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def rotate_secret(self, app_id: int, app_secret: str) -> Application | None:
        """只轮换 app_secret，site_id 不变。"""
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return None
        model.app_secret = app_secret
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    # 向后兼容旧调用名
    async def rotate_api_key(self, app_id: int, new_app_id: str, app_secret: str) -> Application | None:
        """已废弃：site_id 不再变化，new_app_id 参数忽略，仅轮换 secret。"""
        return await self.rotate_secret(app_id, app_secret)

    async def delete(self, app_id: int) -> bool:
        model = await self._session.get(ApplicationModel, app_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def get_rule_stats_for_sites(
        self, site_ids: list[int]
    ) -> dict[int, tuple[str | None, str | None]]:
        """批量查询每个站点绑定的规则名称和状态（一站点最多一条规则）。
        
        返回 {site_id: (rule_name, rule_status)}
        """
        if not site_ids:
            return {}
        stmt = (
            select(
                RuleSiteModel.site_id,
                RuleModel.name,
                RuleModel.status,
            )
            .join(RuleModel, RuleModel.id == RuleSiteModel.rule_id)
            .where(RuleSiteModel.site_id.in_(site_ids))
            .limit(len(site_ids) * 2)  # 防御性上限
        )
        rows = (await self._session.execute(stmt)).all()
        result: dict[int, tuple[str | None, str | None]] = {}
        for sid, name, status in rows:
            if sid not in result:  # 取第一条
                result[sid] = (name, status)
        return result

    @staticmethod
    def _to_domain(row: ApplicationModel | None) -> Application | None:
        if row is None:
            return None
        return Application(
            id=row.id,
            site_id=row.site_id,
            name=row.name,
            domain=row.domain,
            alt_domains=list(row.alt_domains or []),
            access_mode=row.access_mode,
            app_secret=row.app_secret,
            sdk_version=row.sdk_version,
            gateway_url=row.gateway_url,
            is_active=row.is_active,
            owner_user_id=row.owner_user_id,
            clock_stats_enabled=row.clock_stats_enabled,
            log_retention_days=row.log_retention_days,
            remark=row.remark,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

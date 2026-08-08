"""站点（Site）仓储 - V3 两层架构。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import SiteModel, RuleSiteModel, RuleModel


def _gen_site_key() -> str:
    """生成站点标识，格式 site_<hex8>，同时作为 X-App-Key 使用。"""
    return f"site_{uuid.uuid4().hex[:8]}"


class SiteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, site_id: int) -> SiteModel | None:
        return await self._session.get(SiteModel, site_id)

    async def get_by_site_key(self, site_key: str) -> SiteModel | None:
        stmt = select(SiteModel).where(SiteModel.site_key == site_key).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_app(self, app_id: int) -> list[SiteModel]:
        """获取应用下的所有站点。"""
        stmt = select(SiteModel).where(SiteModel.app_id == app_id).order_by(SiteModel.id.desc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_active_bindings(self) -> list[tuple[str, int, int, str]]:
        """启动引导：拉 (site_key, site_id, app_id, site_secret)，用于全量刷新 Redis 映射。"""
        stmt = select(
            SiteModel.site_key,
            SiteModel.id,
            SiteModel.app_id,
            SiteModel.site_secret,
        ).where(SiteModel.is_active.is_(True))
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1], row[2], row[3] or "") for row in rows if row[0] and row[1]]

    async def list_paged(
        self,
        *,
        keyword: str | None = None,
        app_id: int | None = None,
        is_active: bool | None = None,
        access_mode: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[SiteModel], int]:
        base = select(SiteModel)
        if keyword:
            like = f"%{keyword}%"
            base = base.where(
                or_(
                    SiteModel.name.ilike(like),
                    SiteModel.domain.ilike(like),
                    SiteModel.site_key.ilike(like),
                )
            )
        if app_id is not None:
            base = base.where(SiteModel.app_id == app_id)
        if is_active is not None:
            base = base.where(SiteModel.is_active.is_(is_active))
        if access_mode is not None:
            base = base.where(SiteModel.access_mode == access_mode)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(SiteModel.id.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total)

    async def create(
        self,
        *,
        site_key: str | None = None,
        app_id: int,
        name: str,
        domain: str,
        alt_domains: list[str] | None = None,
        access_mode: str = "adapter",
        site_secret: str = "",
        sdk_version: str | None = None,
        gateway_url: str | None = None,
        is_active: bool = True,
        clock_stats_enabled: bool = True,
        log_retention_days: int = 30,
        remark: str | None = None,
    ) -> SiteModel:
        model = SiteModel(
            site_key=site_key or _gen_site_key(),
            app_id=app_id,
            name=name,
            domain=domain,
            alt_domains=alt_domains or [],
            access_mode=access_mode,
            site_secret=site_secret,
            sdk_version=sdk_version,
            gateway_url=gateway_url,
            is_active=is_active,
            clock_stats_enabled=clock_stats_enabled,
            log_retention_days=log_retention_days,
            remark=remark,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def update(
        self,
        site_id: int,
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
    ) -> SiteModel | None:
        model = await self._session.get(SiteModel, site_id)
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
        return model

    async def rotate_secret(self, site_id: int, site_secret: str) -> SiteModel | None:
        """轮换站点密钥。"""
        model = await self._session.get(SiteModel, site_id)
        if model is None:
            return None
        model.site_secret = site_secret
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def delete(self, site_id: int) -> bool:
        model = await self._session.get(SiteModel, site_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def get_rule_stats_for_sites(
        self, site_ids: list[int]
    ) -> dict[int, list[tuple[str, str]]]:
        """批量查询每个站点绑定的规则名称和状态列表。
        
        返回 {site_id: [(rule_name, rule_status), ...]}
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
            .order_by(RuleSiteModel.site_id, RuleModel.id)
        )
        rows = (await self._session.execute(stmt)).all()
        result: dict[int, list[tuple[str, str]]] = {sid: [] for sid in site_ids}
        for sid, name, status in rows:
            result[sid].append((name, status))
        return result

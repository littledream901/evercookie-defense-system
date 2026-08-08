"""站点管理服务（V3 两层架构）。

站点是规则、页面资源、频控的挂载点，也是 gateway 验签的身份主体。
除 DB 落库外还负责把 ``site_key → site_id`` 映射同步到 Redis，
否则 gateway 的 AppKeyResolver 认不出新建站点，请求一律 401。
"""

from __future__ import annotations

import secrets

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.infrastructure.cache.app_key_sync import AppKeyRedisSync
from src.infrastructure.repositories.models import SiteModel
from src.infrastructure.repositories.site_repository import SiteRepository

_logger = get_logger("admin.site_service")

_ACCESS_MODES = frozenset({"adapter", "sdk"})


class SiteService:
    def __init__(
        self,
        site_repo: SiteRepository,
        *,
        app_key_sync: AppKeyRedisSync | None = None,
    ) -> None:
        self._repo = site_repo
        self._app_key_sync = app_key_sync

    async def get(self, site_id: int) -> SiteModel:
        site = await self._repo.get(site_id)
        if site is None:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")
        return site

    async def list_by_app(self, app_id: int) -> list[SiteModel]:
        return await self._repo.list_by_app(app_id)

    async def list_paged(
        self,
        *,
        keyword: str | None = None,
        app_id: int | None = None,
        is_active: bool | None = None,
        access_mode: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SiteModel], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_paged(
            keyword=keyword,
            app_id=app_id,
            is_active=is_active,
            access_mode=access_mode,
            offset=offset,
            limit=page_size,
        )

    async def get_rule_stats(self, site_ids: list[int]) -> dict[int, list[tuple[str, str]]]:
        return await self._repo.get_rule_stats_for_sites(site_ids)

    async def create(
        self,
        *,
        app_id: int,
        name: str,
        domain: str,
        alt_domains: list[str] | None = None,
        access_mode: str = "adapter",
        sdk_version: str | None = None,
        gateway_url: str | None = None,
        clock_stats_enabled: bool = True,
        log_retention_days: int = 30,
        remark: str | None = None,
    ) -> tuple[SiteModel, str]:
        """创建站点，返回 (站点, 密钥明文)。密钥仅此一次可见。"""
        if not name:
            raise ValidationException("站点名不能为空")
        if not domain:
            raise ValidationException("主域名不能为空")
        if access_mode and access_mode not in _ACCESS_MODES:
            raise ValidationException(f"接入模式无效: {access_mode}")

        site_secret = _generate_site_secret()
        site = await self._repo.create(
            app_id=app_id,
            name=name,
            domain=domain,
            alt_domains=alt_domains or [],
            access_mode=access_mode,
            site_secret=site_secret,
            sdk_version=sdk_version,
            gateway_url=gateway_url,
            clock_stats_enabled=clock_stats_enabled,
            log_retention_days=log_retention_days,
            remark=remark,
        )
        await self._sync_bind(site, secret=site_secret)
        _logger.info("site_created", site_id=site.id, app_id=app_id)
        return site, site_secret

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
    ) -> SiteModel:
        existing = await self._repo.get(site_id)
        if existing is None:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")

        if access_mode and access_mode not in _ACCESS_MODES:
            raise ValidationException(f"接入模式无效: {access_mode}")

        updated = await self._repo.update(
            site_id,
            name=name,
            alt_domains=alt_domains,
            access_mode=access_mode,
            sdk_version=sdk_version,
            gateway_url=gateway_url,
            is_active=is_active,
            clock_stats_enabled=clock_stats_enabled,
            log_retention_days=log_retention_days,
            remark=remark,
        )
        if updated is None:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")

        # 启停时同步 Redis
        if is_active is False:
            await self._sync_unbind(existing.site_key, site_id)
        elif is_active is True:
            await self._sync_bind(updated)

        _logger.info("site_updated", site_id=site_id)
        return updated

    async def rotate_secret(self, site_id: int) -> tuple[SiteModel, str]:
        """轮换站点密钥，返回 (站点, 新密钥明文)。"""
        existing = await self._repo.get(site_id)
        if existing is None:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")

        site_secret = _generate_site_secret()
        updated = await self._repo.rotate_secret(site_id, site_secret)
        if updated is None:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")

        # site_key 不变，只需更新 Redis 里的 secret
        await self._sync_bind(updated, secret=site_secret)
        _logger.info("site_secret_rotated", site_id=site_id)
        return updated, site_secret

    async def delete(self, site_id: int) -> None:
        site = await self._repo.get(site_id)
        if site is None:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")
        if site.is_active:
            raise BusinessRuleException("激活状态的站点需先停用后再删除")

        success = await self._repo.delete(site_id)
        if not success:
            raise ResourceNotFoundException(f"站点不存在: {site_id}")

        await self._sync_unbind(site.site_key, site_id)
        _logger.info("site_deleted", site_id=site_id)

    async def batch_delete(self, site_ids: list[int]) -> tuple[list[int], list[dict[str, str]]]:
        """逐条删除，单条失败不影响其他项。"""
        succeeded: list[int] = []
        failed: list[dict[str, str]] = []
        for site_id in site_ids:
            try:
                await self.delete(site_id)
                succeeded.append(site_id)
            except (ResourceNotFoundException, BusinessRuleException) as exc:
                failed.append({"id": str(site_id), "reason": str(exc)})
        _logger.info("site_batch_deleted", succeeded=len(succeeded), failed=len(failed))
        return succeeded, failed

    async def batch_set_active(
        self, site_ids: list[int], *, is_active: bool
    ) -> tuple[list[int], list[dict[str, str]]]:
        """批量启停。"""
        succeeded: list[int] = []
        failed: list[dict[str, str]] = []
        for site_id in site_ids:
            try:
                await self.update(
                    site_id,
                    is_active=is_active,
                )
                succeeded.append(site_id)
            except (ResourceNotFoundException, BusinessRuleException) as exc:
                failed.append({"id": str(site_id), "reason": str(exc)})
        _logger.info(
            "site_batch_set_active",
            is_active=is_active,
            succeeded=len(succeeded),
            failed=len(failed),
        )
        return succeeded, failed

    async def batch_update(
        self,
        site_ids: list[int],
        *,
        access_mode: str | None = None,
        clock_stats_enabled: bool | None = None,
        log_retention_days: int | None = None,
    ) -> tuple[list[int], list[dict[str, str]]]:
        """批量修改通用配置。"""
        succeeded: list[int] = []
        failed: list[dict[str, str]] = []
        for site_id in site_ids:
            try:
                await self.update(
                    site_id,
                    access_mode=access_mode,
                    clock_stats_enabled=clock_stats_enabled,
                    log_retention_days=log_retention_days,
                )
                succeeded.append(site_id)
            except (ResourceNotFoundException, BusinessRuleException) as exc:
                failed.append({"id": str(site_id), "reason": str(exc)})
        _logger.info("site_batch_updated", succeeded=len(succeeded), failed=len(failed))
        return succeeded, failed

    async def _sync_bind(self, site: SiteModel, *, secret: str | None = None) -> None:
        """同步 site_key → site.id 映射到 Redis，gateway 验签依赖此映射。"""
        if self._app_key_sync is None or site.id is None:
            return
        effective_secret = secret or site.site_secret
        # 注意：Redis JSON 字段名仍用 app_id/app_secret，与 gateway 约定保持一致
        await self._app_key_sync.bind(site.site_key, site.id, effective_secret)

    async def _sync_unbind(self, site_key: str, site_id: int | None = None) -> None:
        """解绑 Redis 映射。传 site_id 时连带清理反向索引（仅用于删除）。"""
        if self._app_key_sync is None:
            return
        await self._app_key_sync.unbind(site_key, site_id)


def _generate_site_secret() -> str:
    """验签密钥：hex 格式，与 site_key 格式明显区分。"""
    return secrets.token_hex(24)


__all__ = ["SiteService"]

"""页面资源管理服务。"""

from __future__ import annotations

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
)
from fangyu_shared.logging import get_logger

from src.domain.page_resource.entities import PageResource, PageResourceKind
from src.infrastructure.cache.page_resource_cache import PageResourceCache
from src.infrastructure.repositories.page_resource_repository import (
    PageResourceRepository,
)

_logger = get_logger("admin.page_resource_service")


class PageResourceService:
    def __init__(
        self,
        *,
        resource_repo: PageResourceRepository,
        resource_cache: PageResourceCache,
    ) -> None:
        self._repo = resource_repo
        self._cache = resource_cache

    async def list_by_app(
        self,
        site_id: int,
        *,
        kind: PageResourceKind | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PageResource], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_by_app(
            site_id,
            kind=kind,
            enabled=enabled,
            offset=offset,
            limit=page_size,
        )

    async def get(self, resource_id: int) -> PageResource:
        resource = await self._repo.get(resource_id)
        if resource is None:
            raise ResourceNotFoundException(f"页面资源不存在: {resource_id}")
        return resource

    async def create(self, resource: PageResource) -> PageResource:
        # 检查名称冲突
        existing = await self._repo.get_by_name(resource.site_id, resource.name)
        if existing is not None:
            raise BusinessRuleException(
                f"资源名称已存在: {resource.name} (site={resource.site_id})"
            )
        created = await self._repo.create(resource)
        if created.enabled:
            await self._cache.upsert(created)
        _logger.info(
            "page_resource_created",
            resource_id=created.id,
            site_id=created.site_id,
            name=created.name,
        )
        return created

    async def update(self, resource_id: int, patch: PageResource) -> PageResource:
        current = await self._repo.get(resource_id)
        if current is None:
            raise ResourceNotFoundException(f"页面资源不存在: {resource_id}")
        # 如果改名，检查新名称是否冲突
        if patch.name != current.name:
            existing = await self._repo.get_by_name(current.site_id, patch.name)
            if existing is not None and existing.id != resource_id:
                raise BusinessRuleException(
                    f"资源名称已存在: {patch.name} (site={current.site_id})"
                )
        current.name = patch.name
        current.kind = patch.kind
        current.content = patch.content
        current.content_type = patch.content_type
        current.enabled = patch.enabled
        updated = await self._repo.update(current)
        if updated.enabled:
            await self._cache.upsert(updated)
        else:
            # disabled → 从缓存移除
            await self._cache.remove(updated.site_id, updated.name)
        _logger.info(
            "page_resource_updated",
            resource_id=resource_id,
            name=updated.name,
            enabled=updated.enabled,
        )
        return updated

    async def delete(self, resource_id: int) -> None:
        resource = await self._repo.get(resource_id)
        if resource is None:
            raise ResourceNotFoundException(f"页面资源不存在: {resource_id}")
        await self._repo.delete(resource_id)
        await self._cache.remove(resource.site_id, resource.name)
        _logger.info(
            "page_resource_deleted",
            resource_id=resource_id,
            site_id=resource.site_id,
            name=resource.name,
        )

    async def sync_enabled_to_cache(self, site_id: int) -> int:
        """同步站点的所有已启用资源到 Redis（admin 端批量 publish 时）。"""
        resources, _ = await self._repo.list_by_app(site_id, enabled=True, limit=9999)
        await self._cache.sync_app_resources(site_id, resources)
        _logger.info(
            "page_resource_cache_synced", site_id=site_id, count=len(resources)
        )
        return len(resources)

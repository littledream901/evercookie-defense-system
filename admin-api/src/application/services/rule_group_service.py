"""规则组管理服务。"""

from __future__ import annotations

from fangyu_shared.exceptions import ResourceNotFoundException
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.disposition import Disposition
from fangyu_shared.schemas.rule import GroupMode, RuleGroup, RulePriority

from src.infrastructure.cache.rule_group_cache import RuleGroupCache
from src.infrastructure.repositories.rule_group_repository import RuleGroupRepository

_logger = get_logger("admin.rule_group_service")


class RuleGroupService:
    def __init__(self, repo: RuleGroupRepository, cache: RuleGroupCache) -> None:
        self._repo = repo
        self._cache = cache

    async def get(self, group_id: int) -> RuleGroup:
        """获取规则组详情。"""
        group = await self._repo.get(group_id)
        if group is None:
            raise ResourceNotFoundException(f"规则组 {group_id} 不存在")
        return group

    async def list_by_site(self, site_id: int) -> list[RuleGroup]:
        """查询某站点的所有规则组。"""
        return await self._repo.list_by_site(site_id)

    async def create(
        self,
        site_id: int,
        name: str,
        mode: GroupMode,
        priority: RulePriority,
        enabled: bool,
        on_no_match: Disposition | None,
    ) -> RuleGroup:
        """创建规则组。"""
        group = await self._repo.create(site_id, name, mode, priority, enabled, on_no_match)
        
        # 同步到 Redis
        if group.enabled:
            await self._cache.upsert_one(group)
        
        _logger.info("rule_group_created", group_id=group.id, site_id=site_id, name=name)
        return group

    async def update(
        self,
        group_id: int,
        name: str | None = None,
        mode: GroupMode | None = None,
        priority: RulePriority | None = None,
        enabled: bool | None = None,
        on_no_match: Disposition | None = None,
    ) -> RuleGroup:
        """更新规则组。"""
        group = await self._repo.update(group_id, name, mode, priority, enabled, on_no_match)
        if group is None:
            raise ResourceNotFoundException(f"规则组 {group_id} 不存在")
        
        # 同步到 Redis
        await self._cache.upsert_one(group)
        
        _logger.info("rule_group_updated", group_id=group_id)
        return group

    async def delete(self, group_id: int) -> None:
        """删除规则组。"""
        group = await self._repo.get(group_id)
        if group is None:
            raise ResourceNotFoundException(f"规则组 {group_id} 不存在")
        
        success = await self._repo.delete(group_id)
        if success:
            # 从 Redis 移除
            await self._cache.remove_one(group.site_id, group_id)
            _logger.info("rule_group_deleted", group_id=group_id, site_id=group.site_id)

    async def sync_site_to_cache(self, site_id: int) -> int:
        """全量同步某站点的规则组到 Redis。"""
        groups = await self._repo.list_by_site(site_id)
        enabled_groups = [g for g in groups if g.enabled]
        await self._cache.replace_site(site_id, enabled_groups)
        _logger.info("rule_group_cache_synced", site_id=site_id, count=len(enabled_groups))
        return len(enabled_groups)

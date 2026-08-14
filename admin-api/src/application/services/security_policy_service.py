"""安全策略服务。"""

from __future__ import annotations

from fangyu_shared.schemas.security import SecurityPolicy

from src.infrastructure.repositories.security_policy_repository import SecurityPolicyRepository
from src.infrastructure.security_policy_sync import SecurityPolicySync


class SecurityPolicyService:
    """安全策略服务。"""

    def __init__(self, repo: SecurityPolicyRepository, sync: SecurityPolicySync) -> None:
        self._repo = repo
        self._sync = sync

    async def get_policy(self, site_id: int) -> SecurityPolicy:
        """获取站点安全策略配置，未配置时返回默认值。"""
        policy = await self._repo.get(site_id)
        if policy is None:
            # 返回默认配置（全部启用 + deny）
            return SecurityPolicy(siteId=site_id)
        return policy

    async def update_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        """更新站点安全策略配置并同步到 Redis。"""
        updated = await self._repo.upsert(policy)
        await self._sync.sync(updated)
        return updated

    async def reset_policy(self, site_id: int) -> bool:
        """重置站点安全策略为默认值（删除配置记录和 Redis 缓存）。"""
        deleted = await self._repo.delete(site_id)
        if deleted:
            await self._sync.delete(site_id)
        return deleted

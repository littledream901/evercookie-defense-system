"""流水线配置服务层。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fangyu_shared.schemas.pipeline import PipelineConfig

if TYPE_CHECKING:
    from src.infrastructure.repositories.pipeline_config_repository import PipelineConfigRepository
    from src.infrastructure.pipeline_config_sync import PipelineConfigSync


class PipelineConfigService:
    """流水线配置服务。"""

    def __init__(self, repo: PipelineConfigRepository, sync: PipelineConfigSync | None = None) -> None:
        self._repo = repo
        self._sync = sync

    async def get_config(self, site_id: int) -> PipelineConfig:
        """获取站点的流水线配置。未配置时返回默认值（全部启用）。"""
        config = await self._repo.get_by_site(site_id)
        if config is None:
            # 返回默认配置：所有阶段均启用
            return PipelineConfig(
                siteId=site_id,
                whitelistEnabled=True,
                clockEnabled=True,
                threatIntelEnabled=True,
                securityEnabled=True,
                rulesEnabled=True,
                scoringEnabled=True,
            )
        return config

    async def update_config(self, site_id: int, config: PipelineConfig) -> PipelineConfig:
        """更新流水线配置并同步到 Redis。"""
        # 确保 siteId 一致
        config.site_id = site_id
        updated = await self._repo.update(site_id, config)
        
        # 同步到 Redis（供 Gateway 读取）
        if self._sync is not None:
            await self._sync.sync(site_id, updated)
        
        return updated

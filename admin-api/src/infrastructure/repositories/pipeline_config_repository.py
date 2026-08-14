"""流水线配置仓储层。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fangyu_shared.schemas.pipeline import PipelineConfig

from .models import DefaultDispositionModel

if TYPE_CHECKING:
    pass


class PipelineConfigRepository:
    """流水线配置仓储（复用 biz_default_disposition 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_site(self, site_id: int) -> PipelineConfig | None:
        """获取站点的流水线配置。"""
        stmt = select(DefaultDispositionModel).where(DefaultDispositionModel.site_id == site_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        return PipelineConfig(
            siteId=row.site_id,
            whitelistEnabled=row.whitelist_enabled,
            clockEnabled=row.clock_enabled,
            threatIntelEnabled=row.threat_intel_enabled,
            securityEnabled=row.security_enabled,
            rulesEnabled=row.rules_enabled,
            scoringEnabled=row.scoring_enabled,
        )

    async def update(self, site_id: int, config: PipelineConfig) -> PipelineConfig:
        """更新流水线配置（如果记录不存在则创建）。"""
        stmt = select(DefaultDispositionModel).where(DefaultDispositionModel.site_id == site_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            # 创建新记录（disposition 为必填，设为 None 表示无默认处置）
            row = DefaultDispositionModel(
                site_id=site_id,
                disposition=None,
                whitelist_enabled=config.whitelist_enabled,
                clock_enabled=config.clock_enabled,
                threat_intel_enabled=config.threat_intel_enabled,
                security_enabled=config.security_enabled,
                rules_enabled=config.rules_enabled,
                scoring_enabled=config.scoring_enabled,
            )
            self._session.add(row)
        else:
            # 更新现有记录
            row.whitelist_enabled = config.whitelist_enabled
            row.clock_enabled = config.clock_enabled
            row.threat_intel_enabled = config.threat_intel_enabled
            row.security_enabled = config.security_enabled
            row.rules_enabled = config.rules_enabled
            row.scoring_enabled = config.scoring_enabled

        await self._session.flush()
        await self._session.refresh(row)

        return PipelineConfig(
            siteId=row.site_id,
            whitelistEnabled=row.whitelist_enabled,
            clockEnabled=row.clock_enabled,
            threatIntelEnabled=row.threat_intel_enabled,
            securityEnabled=row.security_enabled,
            rulesEnabled=row.rules_enabled,
            scoringEnabled=row.scoring_enabled,
        )

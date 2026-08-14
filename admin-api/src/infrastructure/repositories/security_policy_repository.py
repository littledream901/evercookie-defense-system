"""安全策略仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fangyu_shared.schemas.security import (
    SecurityPolicy,
    SecurityPolicyAction,
    ScannerPolicy,
    ThreatIntelPolicy,
    TorPolicy,
    VpnDatacenterPolicy,
)

from .models import SecurityPolicyModel


class SecurityPolicyRepository:
    """安全策略仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, site_id: int) -> SecurityPolicy | None:
        """获取站点安全策略配置。"""
        stmt = select(SecurityPolicyModel).where(SecurityPolicyModel.site_id == site_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_domain(row)

    async def upsert(self, policy: SecurityPolicy) -> SecurityPolicy:
        """创建或更新安全策略配置。"""
        stmt = select(SecurityPolicyModel).where(SecurityPolicyModel.site_id == policy.site_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            # 创建新记录
            row = SecurityPolicyModel(
                site_id=policy.site_id,
                enabled=policy.enabled,
                threat_intel_enabled=policy.threat_intel.enabled,
                threat_intel_action=policy.threat_intel.action.value,
                threat_intel_score=policy.threat_intel.score,
                scanner_enabled=policy.scanner.enabled,
                scanner_action=policy.scanner.action.value,
                scanner_score=policy.scanner.score,
                vpn_datacenter_enabled=policy.vpn_datacenter.enabled,
                vpn_datacenter_action=policy.vpn_datacenter.action.value,
                vpn_datacenter_score=policy.vpn_datacenter.score,
                tor_enabled=policy.tor.enabled,
                tor_action=policy.tor.action.value,
                tor_score=policy.tor.score,
            )
            self._session.add(row)
        else:
            # 更新现有记录
            row.enabled = policy.enabled
            row.threat_intel_enabled = policy.threat_intel.enabled
            row.threat_intel_action = policy.threat_intel.action.value
            row.threat_intel_score = policy.threat_intel.score
            row.scanner_enabled = policy.scanner.enabled
            row.scanner_action = policy.scanner.action.value
            row.scanner_score = policy.scanner.score
            row.vpn_datacenter_enabled = policy.vpn_datacenter.enabled
            row.vpn_datacenter_action = policy.vpn_datacenter.action.value
            row.vpn_datacenter_score = policy.vpn_datacenter.score
            row.tor_enabled = policy.tor.enabled
            row.tor_action = policy.tor.action.value
            row.tor_score = policy.tor.score

        await self._session.commit()
        await self._session.refresh(row)
        return self._to_domain(row)

    async def delete(self, site_id: int) -> bool:
        """删除安全策略配置（重置为默认）。"""
        stmt = select(SecurityPolicyModel).where(SecurityPolicyModel.site_id == site_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True

    def _to_domain(self, row: SecurityPolicyModel) -> SecurityPolicy:
        """ORM 模型转领域对象。"""
        return SecurityPolicy(
            siteId=row.site_id,
            enabled=row.enabled,
            threatIntel=ThreatIntelPolicy(
                enabled=row.threat_intel_enabled,
                action=SecurityPolicyAction(row.threat_intel_action),
                score=row.threat_intel_score,
            ),
            scanner=ScannerPolicy(
                enabled=row.scanner_enabled,
                action=SecurityPolicyAction(row.scanner_action),
                score=row.scanner_score,
            ),
            vpnDatacenter=VpnDatacenterPolicy(
                enabled=row.vpn_datacenter_enabled,
                action=SecurityPolicyAction(row.vpn_datacenter_action),
                score=row.vpn_datacenter_score,
            ),
            tor=TorPolicy(
                enabled=row.tor_enabled,
                action=SecurityPolicyAction(row.tor_action),
                score=row.tor_score,
            ),
        )

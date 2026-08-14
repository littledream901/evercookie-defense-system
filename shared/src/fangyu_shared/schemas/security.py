"""安全策略配置领域模型。

威胁情报和安全检查器的可配置化处置策略。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .common import BaseSchema


class SecurityPolicyAction(str, Enum):
    """安全策略处置动作。"""

    DENY = "deny"  # 直接拒绝
    CHALLENGE = "challenge"  # 人机验证
    SCORE = "score"  # 加分项（不直接拦截）


class ThreatIntelPolicy(BaseModel):
    """威胁情报策略。"""

    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=100, ge=0, le=100, description="action=score 时的加分值")


class ScannerPolicy(BaseModel):
    """扫描器检测策略（安全扫描器、爬虫）。"""

    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=80, ge=0, le=100)


class VpnDatacenterPolicy(BaseModel):
    """VPN+数据中心策略（双重匹配）。"""

    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=60, ge=0, le=100)


class TorPolicy(BaseModel):
    """Tor 检测策略。"""

    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=90, ge=0, le=100)


class SecurityPolicy(BaseSchema):
    """站点安全策略（完整配置）。"""

    site_id: int = Field(..., alias="siteId", gt=0)
    enabled: bool = Field(default=True, description="安全策略总开关")
    threat_intel: ThreatIntelPolicy = Field(
        default_factory=ThreatIntelPolicy, alias="threatIntel"
    )
    scanner: ScannerPolicy = Field(default_factory=ScannerPolicy)
    vpn_datacenter: VpnDatacenterPolicy = Field(
        default_factory=VpnDatacenterPolicy, alias="vpnDatacenter"
    )
    tor: TorPolicy = Field(default_factory=TorPolicy)

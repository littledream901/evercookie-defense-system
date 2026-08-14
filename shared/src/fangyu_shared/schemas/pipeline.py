"""流水线配置领域模型。

集中管理决策流水线各阶段的开关，避免硬编码。
"""

from __future__ import annotations

from pydantic import Field

from .common import BaseSchema


class PipelineConfig(BaseSchema):
    """流水线配置（站点级别）。"""

    site_id: int = Field(..., alias="siteId", gt=0)
    
    # 各阶段开关
    whitelist_enabled: bool = Field(default=True, alias="whitelistEnabled", description="白名单阶段开关")
    clock_enabled: bool = Field(default=True, alias="clockEnabled", description="频控阶段开关")
    threat_intel_enabled: bool = Field(default=True, alias="threatIntelEnabled", description="威胁情报阶段开关")
    security_enabled: bool = Field(default=True, alias="securityEnabled", description="安全检查阶段开关")
    rules_enabled: bool = Field(default=True, alias="rulesEnabled", description="规则匹配阶段开关")
    scoring_enabled: bool = Field(default=True, alias="scoringEnabled", description="风险评分阶段开关")

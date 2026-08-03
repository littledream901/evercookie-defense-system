"""决策相关的领域实体与值对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fangyu_shared.schemas.disposition import Disposition

from src.domain.decision.disposition import DecidedBy


class PipelineStage(str, Enum):
    """决策流水线阶段。"""

    WHITELIST = "whitelist"
    CHALLENGE_PASS = "challenge_pass"
    CLOCK = "clock"
    HYBRID_LOOKUP = "hybrid_lookup"
    CACHE = "cache"
    PROFILE = "profile"
    DECISION_RULE = "decision_rule"
    THREAT_INTEL = "threat_intel"
    SECURITY = "security"
    RISK_SCORING = "risk_scoring"
    DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class PipelineStageResult:
    """流水线中单个阶段的结果。"""

    stage: PipelineStage
    disposition: Disposition | None = None
    score: float = 0.0
    rule_ids: tuple[int, ...] = ()
    reason: str | None = None
    matched: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShadowHit:
    """影子规则命中记录：不影响决策，仅用于发布前影响面测算。"""

    rule_id: int | None
    rule_name: str
    disposition: Disposition


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """决策最终结果。

    ``disposition.target.url`` 此时仍是**未渲染**的模板，占位符替换发生在
    响应构造阶段（缓存之后），避免同一访客不同 URL 复用同一渲染结果。
    """

    disposition: Disposition
    decided_by: DecidedBy
    decided_stage: str
    score: float = 0.0
    rule_ids: tuple[int, ...] = ()
    reason: str | None = None
    stage_results: tuple[PipelineStageResult, ...] = ()
    scorer_scores: dict[str, float] = field(default_factory=dict)
    shadow_hits: tuple[ShadowHit, ...] = ()
    challenge_token: str | None = None
    clock_counts: dict[str, int] = field(default_factory=dict)
    """Clock 各窗口计数，键形如 ``ip_burst`` / ``fp_short``。落库供频控调优。"""
    clock_banned: bool = False

    @property
    def ttl_seconds(self) -> int:
        return self.disposition.ttl_seconds

    @property
    def is_cacheable(self) -> bool:
        """决策是否可写入缓存。

        频控/封禁结论与时间强相关，缓存它们会导致窗口滑过后仍被拒。
        """
        return not self.decided_by.is_time_sensitive

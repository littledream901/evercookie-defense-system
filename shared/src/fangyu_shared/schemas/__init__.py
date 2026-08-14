"""跨服务共享的 Pydantic 数据契约。"""

from __future__ import annotations

from fangyu_shared.schemas.clock import BehaviorEvent, ClockLimits, default_limits
from fangyu_shared.schemas.common import (
    ErrorResponse,
    HealthCheckResponse,
    PageRequest,
    PageResponse,
    SuccessResponse,
)
from fangyu_shared.schemas.decision import (
    DecisionContext,
    DecisionDetail,
    DecisionRequest,
    DecisionResponse,
    IngressKind,
    ShadowOutcome,
)
from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    Disposition,
    Mechanism,
    Target,
    TargetKind,
    Verdict,
)
from fangyu_shared.schemas.event import (
    DecisionEvent,
    EventBatch,
    EventBatchAck,
)
from fangyu_shared.schemas.pipeline import PipelineConfig
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile
from fangyu_shared.schemas.rule import (
    DecisionRule,
    GroupMode,
    RuleCondition,
    RuleGroup,
    RulePriority,
    RuleSet,
    RuleStatus,
)
from fangyu_shared.schemas.security import (
    ScannerPolicy,
    SecurityPolicy,
    SecurityPolicyAction,
    ThreatIntelPolicy,
    TorPolicy,
    VpnDatacenterPolicy,
)
from fangyu_shared.schemas.target_render import pick_target, render_pool, render_target

__all__ = [
    "BehaviorEvent",
    "ChallengeKind",
    "ClockLimits",
    "DecisionContext",
    "DecisionDetail",
    "DecisionEvent",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionRule",
    "DeviceProfile",
    "Disposition",
    "ErrorResponse",
    "EventBatch",
    "EventBatchAck",
    "GroupMode",
    "HealthCheckResponse",
    "IngressKind",
    "IpProfile",
    "Mechanism",
    "PageRequest",
    "PageResponse",
    "PipelineConfig",
    "RuleCondition",
    "RuleGroup",
    "RulePriority",
    "RuleSet",
    "RuleStatus",
    "ScannerPolicy",
    "SecurityPolicy",
    "SecurityPolicyAction",
    "ShadowOutcome",
    "SuccessResponse",
    "Target",
    "TargetKind",
    "ThreatIntelPolicy",
    "TorPolicy",
    "Verdict",
    "VpnDatacenterPolicy",
    "default_limits",
    "pick_target",
    "render_pool",
    "render_target",
]

"""处置解析：把各阶段产出汇聚成最终 Disposition，并记录来源。

与旧版的差异
------------
旧版 ``default_disposition`` 是一个 40 行函数，7 级回退里散落着对
``action``/``explain``/``source`` 三个变量的反复赋值，无法单测。本模块把
每一级来源表达为一个独立的具名工厂方法，各自返回带 ``decided_by`` 的
:class:`ResolvedDisposition`，可逐个单测；优先级顺序由调用方（流水线）
显式表达，而不是埋在一个长函数的控制流里。

``decided_by`` 是排障第一现场——风控系统最高频的运维问题是「这个请求为什么
被拦」，没有溯源字段就只能靠猜。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fangyu_shared.schemas.disposition import Disposition, allow


class DecidedBy(str, Enum):
    """处置来源。落库后支撑「为什么是这个处置」的查询。"""

    CLOCK_BAN = "clock_ban"
    CLOCK_RATE_LIMIT = "clock_rate_limit"
    DECISION_RULE = "decision_rule"
    GROUP_NO_MATCH = "group_no_match"
    THREAT_INTEL = "threat_intel"
    SECURITY = "security"
    SCORING = "scoring"
    APP_DEFAULT = "app_default"
    SYSTEM_DEFAULT = "system_default"

    @property
    def is_time_sensitive(self) -> bool:
        """结论是否与时间强相关，不可写入决策缓存。

        频控与封禁的结论只在当前时间窗内成立。若按 ``ttl_seconds`` 缓存，
        访客在窗口早已滑过之后仍会被拒——这类误伤极难排查，因为规则侧
        看不出任何拦截原因。
        """
        return self in (DecidedBy.CLOCK_BAN, DecidedBy.CLOCK_RATE_LIMIT)


@dataclass(frozen=True, slots=True)
class ResolvedDisposition:
    """最终处置 + 溯源信息。"""

    disposition: Disposition
    decided_by: DecidedBy
    decided_stage: str
    rule_id: int | None = None
    rule_name: str | None = None
    reason: str | None = None

    @property
    def explain(self) -> str:
        """人可读的处置来源说明。"""
        if self.rule_name:
            return f"{self.decided_by.value}:{self.rule_name}"
        if self.reason:
            return f"{self.decided_by.value}:{self.reason}"
        return self.decided_by.value


SYSTEM_DEFAULT_DISPOSITION = allow()
"""系统兜底处置。

放行而非拦截是有意选择：兜底被触发意味着规则配置未覆盖该流量，此时拦截
会造成大面积误伤。真正的 fail-closed 收敛在规则校验期（空条件规则直接拒绝
创建），而非运行期兜底。
"""


class DispositionResolver:
    """处置解析器：按固定优先级选出最终处置。"""

    @staticmethod
    def from_clock_ban(disposition: Disposition, *, reason: str) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.CLOCK_BAN,
            decided_stage="clock",
            reason=reason,
        )

    @staticmethod
    def from_clock_rate_limit(
        disposition: Disposition, *, reason: str
    ) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.CLOCK_RATE_LIMIT,
            decided_stage="clock",
            reason=reason,
        )

    @staticmethod
    def from_rule(
        disposition: Disposition,
        *,
        rule_id: int | None,
        rule_name: str,
        stage: str = "decision_rule",
    ) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.DECISION_RULE,
            decided_stage=stage,
            rule_id=rule_id,
            rule_name=rule_name,
        )

    @staticmethod
    def from_group_no_match(
        disposition: Disposition, *, group_name: str
    ) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.GROUP_NO_MATCH,
            decided_stage="decision_rule",
            rule_name=group_name,
            reason=f"allowlist_no_match:{group_name}",
        )

    @staticmethod
    def from_threat_intel(disposition: Disposition, *, reason: str) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.THREAT_INTEL,
            decided_stage="threat_intel",
            reason=reason,
        )

    @staticmethod
    def from_security(disposition: Disposition, *, reason: str) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.SECURITY,
            decided_stage="security",
            reason=reason,
        )

    @staticmethod
    def from_scoring(disposition: Disposition, *, reason: str | None) -> ResolvedDisposition:
        return ResolvedDisposition(
            disposition=disposition,
            decided_by=DecidedBy.SCORING,
            decided_stage="risk_scoring",
            reason=reason,
        )

    @staticmethod
    def fallback(app_default: Disposition | None) -> ResolvedDisposition:
        """兜底链：app 级默认 → 系统默认。"""
        if app_default is not None:
            return ResolvedDisposition(
                disposition=app_default,
                decided_by=DecidedBy.APP_DEFAULT,
                decided_stage="default",
                reason="app_default_disposition",
            )
        return ResolvedDisposition(
            disposition=SYSTEM_DEFAULT_DISPOSITION,
            decided_by=DecidedBy.SYSTEM_DEFAULT,
            decided_stage="default",
            reason="system_default",
        )

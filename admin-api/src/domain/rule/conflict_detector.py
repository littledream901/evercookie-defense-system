"""规则冲突检测器

在站点绑定规则时检测潜在冲突，避免配置错误。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fangyu_shared.schemas.rule import DecisionRule, RuleCondition, RulePriority, RuleStatus


class ConflictSeverity(str, Enum):
    """冲突严重性"""
    HIGH = "high"      # 规则完全失效
    MEDIUM = "medium"  # 部分失效或配置冗余
    LOW = "low"        # 潜在问题或优化建议


@dataclass
class RuleConflict:
    """规则冲突"""
    type: str
    severity: ConflictSeverity
    rule_ids: list[int]
    rule_names: list[str]
    message: str
    suggestion: str | None = None


class RuleConflictDetector:
    """规则冲突检测器
    
    检测站点绑定的多条规则之间的冲突：
    1. 优先级覆盖冲突（高优先级规则完全覆盖低优先级规则）
    2. 字段拼写错误（常见的 camelCase 错误）
    """
    
    # 优先级顺序（数字越小优先级越高）
    _PRIORITY_ORDER = {
        RulePriority.CRITICAL: 0,
        RulePriority.HIGH: 1,
        RulePriority.NORMAL: 2,
        RulePriority.LOW: 3,
    }
    
    # 常见字段拼写错误映射（错误 -> 正确）
    _COMMON_TYPOS = {
        "ip.is_proxy": "ip.isProxy",
        "ip.is_vpn": "ip.isVpn",
        "ip.is_tor": "ip.isTor",
        "ip.is_datacenter": "ip.isDatacenter",
        "ip.is_mobile_network": "ip.isMobileNetwork",
        "ip.ip_type": "ip.ipType",
        "ip.asn_org": "ip.asnOrg",
        "ip.connection_type": "ip.connectionType",
        "ip.reputation_score": "ip.reputationScore",
        "ip.reputation_samples": "ip.reputationSamples",
        "ip.total_requests": "ip.totalRequests",
        "ip.last_seen_at": "ip.lastSeenAt",
        "ua.device_type": "ua.device_type",  # snake_case 是正确的
        "ua.is_bot": "ua.is_bot",
        "ua.is_mobile": "ua.is_mobile",
        "ua.is_empty": "ua.is_empty",
    }
    
    def detect(self, rules: list[DecisionRule]) -> list[RuleConflict]:
        """检测规则列表中的所有冲突
        
        Args:
            rules: 已发布的规则列表
            
        Returns:
            冲突列表
        """
        conflicts: list[RuleConflict] = []
        
        # 只检测已发布的规则
        published_rules = [r for r in rules if r.status == RuleStatus.PUBLISHED]
        
        if len(published_rules) < 2:
            # 字段拼写错误检测不需要多条规则
            conflicts.extend(self._detect_field_typo(rules))
            return conflicts
        
        # 检测优先级覆盖冲突
        conflicts.extend(self._detect_priority_override(published_rules))
        
        # 检测字段拼写错误
        conflicts.extend(self._detect_field_typo(published_rules))
        
        return conflicts
    
    def _detect_priority_override(self, rules: list[DecisionRule]) -> list[RuleConflict]:
        """检测优先级覆盖冲突
        
        高优先级规则的条件如果覆盖低优先级规则，低优先级规则永远不会执行。
        """
        conflicts = []
        
        # 按优先级排序（高优先级在前）
        sorted_rules = sorted(rules, key=lambda r: self._PRIORITY_ORDER[r.priority])
        
        for i, high_rule in enumerate(sorted_rules):
            for low_rule in sorted_rules[i + 1:]:
                # 检查是否存在条件包含关系
                if self._conditions_contain(high_rule.conditions, low_rule.conditions):
                    conflicts.append(RuleConflict(
                        type="priority_override",
                        severity=ConflictSeverity.HIGH,
                        rule_ids=[high_rule.id, low_rule.id],
                        rule_names=[high_rule.name, low_rule.name],
                        message=(
                            f"规则 '{low_rule.name}' ({low_rule.priority.value}) "
                            f"可能被高优先级规则 '{high_rule.name}' ({high_rule.priority.value}) 覆盖，"
                            f"导致永远不会执行"
                        ),
                        suggestion=(
                            f"建议：1) 调整规则 '{low_rule.name}' 的优先级使其更高，"
                            f"或 2) 修改条件使其不与 '{high_rule.name}' 重叠"
                        )
                    ))
        
        return conflicts
    
    def _conditions_contain(
        self, 
        high_conditions: list[RuleCondition], 
        low_conditions: list[RuleCondition]
    ) -> bool:
        """检查高优先级规则的条件是否包含低优先级规则的条件
        
        简化版本：只检测字段完全相同的情况
        """
        high_fields = {c.field for c in high_conditions}
        low_fields = {c.field for c in low_conditions}
        
        # 如果低优先级规则的所有字段都在高优先级规则中，则可能存在覆盖
        if low_fields.issubset(high_fields):
            # 进一步检查：相同字段的条件是否有包含关系
            for low_cond in low_conditions:
                high_cond = next((c for c in high_conditions if c.field == low_cond.field), None)
                if high_cond and self._condition_contains(high_cond, low_cond):
                    return True
        
        return False
    
    def _condition_contains(self, high_cond: RuleCondition, low_cond: RuleCondition) -> bool:
        """检查单个条件是否存在包含关系
        
        简化版本：只检测明显的包含情况
        """
        # 相同字段、相同操作符、相同值 -> 完全重复
        if (high_cond.field == low_cond.field and 
            high_cond.op == low_cond.op and 
            high_cond.value == low_cond.value):
            return True
        
        # in 操作符的包含检查
        if (high_cond.field == low_cond.field and 
            high_cond.op in ("in", "in_ci") and 
            low_cond.op in ("eq", "in", "in_ci")):
            # 如果高优先级是 in，低优先级是 eq，且值在列表中
            if low_cond.op == "eq" and isinstance(high_cond.value, list):
                return low_cond.value in high_cond.value
            # 如果都是 in，检查是否为子集
            if isinstance(high_cond.value, list) and isinstance(low_cond.value, list):
                return set(low_cond.value).issubset(set(high_cond.value))
        
        return False
    
    def _detect_field_typo(self, rules: list[DecisionRule]) -> list[RuleConflict]:
        """检测字段拼写错误
        
        检测常见的 camelCase 和 snake_case 混用错误。
        """
        conflicts = []
        
        for rule in rules:
            typo_fields = []
            for condition in rule.conditions:
                # 检查是否是已知的拼写错误
                if condition.field in self._COMMON_TYPOS:
                    correct = self._COMMON_TYPOS[condition.field]
                    typo_fields.append(f"{condition.field} → {correct}")
            
            if typo_fields:
                conflicts.append(RuleConflict(
                    type="field_typo",
                    severity=ConflictSeverity.MEDIUM,
                    rule_ids=[rule.id],
                    rule_names=[rule.name],
                    message=(
                        f"规则 '{rule.name}' 中检测到字段拼写错误：{', '.join(typo_fields)}"
                    ),
                    suggestion=(
                        f"这些字段永远无法匹配，请修正字段名称。"
                        f"注意 ip.* 命名空间使用 camelCase，ua.* 使用 snake_case"
                    )
                ))
        
        return conflicts
    
    def format_conflicts_for_display(self, conflicts: list[RuleConflict]) -> dict:
        """格式化冲突信息用于前端展示
        
        Returns:
            {
                "has_conflicts": bool,
                "high_severity_count": int,
                "conflicts": [...]
            }
        """
        return {
            "has_conflicts": len(conflicts) > 0,
            "high_severity_count": sum(1 for c in conflicts if c.severity == ConflictSeverity.HIGH),
            "conflicts": [
                {
                    "type": c.type,
                    "severity": c.severity.value,
                    "rule_ids": c.rule_ids,
                    "rule_names": c.rule_names,
                    "message": c.message,
                    "suggestion": c.suggestion,
                }
                for c in conflicts
            ]
        }

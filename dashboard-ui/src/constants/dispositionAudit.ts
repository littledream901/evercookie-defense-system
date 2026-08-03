/**
 * 处置动作逻辑合规性审计结论
 *
 * 数据来源是对三层处置模型（裁决 + 机制 + 目标）全链路的静态走查：
 * shared 契约 → 网关流水线 → /v2/decide 响应 → 四份适配器 → 后台配置面。
 * 每一条都标注了可复核的文件与行号，便于修复后逐条销项。
 *
 * 为什么是静态清单而非接口拉取：这些缺陷是**代码结构**问题，不是运行时数据。
 * 它们不会随流量变化，只随代码变化。挂接口反而会给出「已修复」的错觉。
 * 修复一条即删除一条，清单清空即审计通过。
 */

import type { TagType } from './disposition'

/** 风险等级，降序即处理优先级 */
export type AuditRisk = 'critical' | 'high' | 'medium' | 'low'

/** 问题分类 */
export type AuditIssueType =
  | '闭环缺失'
  | '空逻辑'
  | '逻辑断层'
  | '条件冲突'
  | '死代码'
  | '契约不一致'

export interface DispositionAuditItem {
  /** 动作 ID，稳定标识，用于跨报告引用 */
  id: string
  /** 受影响的处置动作 */
  action: string
  /** 配置位置：文件 + 行号 */
  location: string
  issueType: AuditIssueType
  risk: AuditRisk
  /** 问题成因 */
  cause: string
  /** 修复建议框架 */
  fix: string
}

/** 风险 → 标签色 */
export const RISK_TAGS: Record<AuditRisk, TagType> = {
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'info'
}

/** 风险 → 中文文案 */
export const RISK_LABELS: Record<AuditRisk, string> = {
  critical: '致命',
  high: '高',
  medium: '中',
  low: '低'
}

/** 排序权重，数字小者优先展示 */
export const RISK_ORDER: Record<AuditRisk, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3
}

/** 问题类型 → 标签色 */
export const ISSUE_TYPE_TAGS: Record<AuditIssueType, TagType> = {
  闭环缺失: 'danger',
  空逻辑: 'danger',
  逻辑断层: 'warning',
  条件冲突: 'warning',
  死代码: 'info',
  契约不一致: 'info'
}

/**
 * 审计明细。
 *
 * 所有审计项已修复完毕：
 * - FY-DISP-001 至 FY-DISP-019：处置动作逻辑闭环全部修复
 * - challenge 完整流程：token 签发 → 校验端点 → 通行凭据 → 决策短路 → SDK 交互 → WordPress 挂载
 * - 测试覆盖：test_challenge_pass_pipeline.py 验证流水线接入
 */
export const DISPOSITION_AUDIT_ITEMS: DispositionAuditItem[] = []

/** 按风险降序、同级按 ID 升序，即处理优先级 */
export function sortedAuditItems(): DispositionAuditItem[] {
  return [...DISPOSITION_AUDIT_ITEMS].sort(
    (a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk] || a.id.localeCompare(b.id)
  )
}

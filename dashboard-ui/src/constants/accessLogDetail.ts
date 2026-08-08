/**
 * 访问日志详情常量定义
 * 
 * 用于详情抽屉中的各类标签映射和配置
 */

/** 裁决标签映射 */
export const VERDICT_LABELS: Record<string, string> = {
  trusted: '放行',
  suspect: '可疑',
  hostile: '拦截',
  unknown: '未知'
}

/** 机制标签映射 */
export const MECHANISM_LABELS: Record<string, string> = {
  pass: '放行',
  serve_alt: '替代内容',
  redirect: '跳转',
  challenge: '人机挑战',
  deny: '拒绝',
  not_found: '假装404'
}

/** 评分器名称映射 */
export const SCORER_LABELS: Record<string, string> = {
  ip_reputation: 'IP 声誉',
  proxy: '代理检测',
  user_agent: 'UA 检测',
  interaction: '人机交互',
  device: '设备异常',
  frequency: '访问频率',
  geo: '地理位置',
  behavior: '行为分析',
  fingerprint: '指纹信誉'
}

/** 决策流水线阶段配置 */
export const PIPELINE_STAGES = [
  { key: 'allowlist', label: '白名单', icon: '✓' },
  { key: 'threat_intel', label: '威胁情报', icon: '🛡️' },
  { key: 'hybrid_lookup', label: '混合层查询', icon: '🔍' },
  { key: 'decision_rule', label: '决策规则', icon: '⚙️' },
  { key: 'scoring', label: '风险评分', icon: '📊' },
  { key: 'default', label: '兜底策略', icon: '🎯' }
] as const

/** 连接类型标签映射 */
export const CONNECTION_TYPE_LABELS: Record<string, string> = {
  datacenter: '数据中心',
  hosting: '托管机房',
  business: '企业专线',
  cellular: '移动网络',
  mobile: '移动网络',
  residential: '家庭宽带',
  dialup: '拨号',
  cable: '有线宽带',
  unknown: '未知'
}

/** 操作符显示名称 */
export const OPERATOR_LABELS: Record<string, string> = {
  equals: '等于',
  not_equals: '不等于',
  in: '包含于',
  not_in: '不包含于',
  contains: '包含',
  not_contains: '不包含',
  regex: '正则匹配',
  not_regex: '正则不匹配',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  between: '在范围内',
  exists: '存在',
  not_exists: '不存在'
}

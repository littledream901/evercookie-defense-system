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

/** 机制标签映射
 *
 * 文案刻意与 VERDICT_LABELS 错开：两者同屏展示，若 pass 也叫「放行」
 * 就会与裁决 trusted 的「放行」完全重叠——而稳态下绝大多数流量
 * 正是 trusted + pass，两列文案一模一样，看上去就像机制列填错了裁决值。
 * 机制回答「怎么做」，因此用动作词；裁决回答「为什么」，用判定词。
 */
export const MECHANISM_LABELS: Record<string, string> = {
  pass: '不干预',
  serve_alt: '替代内容',
  redirect: '跳转',
  challenge: '人机验证',
  deny: '403',
  not_found: '404'
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

/**
 * 访问日志格式化工具函数
 * 
 * 用于格式化日志数据的显示
 */

/**
 * UTC 时间转本地时间
 * ClickHouse 返回的 UTC 时间可能不带 Z 后缀，需要手动处理
 * 
 * @param raw 原始时间字符串
 * @returns 格式化后的本地时间
 */
export function formatLogTime(raw?: string | null): string {
  if (!raw) return '-'
  
  // 如果已有时区标识则直接使用，否则补上 Z 表示 UTC
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`
  const d = new Date(iso)
  
  if (isNaN(d.getTime())) return raw
  
  // 转换为本地时区，格式：2024/1/1 16:00:00
  return d.toLocaleString('zh-CN', { hour12: false })
}

/**
 * 风险评分样式类
 * 
 * @param score 风险评分 (0-100)
 * @returns CSS 类名
 */
export function getScoreClass(score?: number | null): string {
  if (score == null) return ''
  if (score >= 75) return 'score-danger'
  if (score >= 30) return 'score-warning'
  return 'score-ok'
}

/**
 * 风险评分卡片样式类
 * 
 * @param score 风险评分 (0-100)
 * @returns CSS 类名
 */
export function getScoreCardClass(score?: number | null): string {
  if (score == null) return 'card-normal'
  if (score >= 75) return 'card-danger'
  if (score >= 30) return 'card-warn'
  return 'card-normal'
}

/**
 * 评分文本类型（ElementPlus）
 * 
 * @param score 风险评分
 * @returns ElementPlus Text 组件的 type 属性值
 */
export function getScoreTextType(score?: number | null): '' | 'danger' | 'warning' | 'success' {
  if (score == null) return ''
  if (score >= 75) return 'danger'
  if (score >= 30) return 'warning'
  return 'success'
}

/**
 * 评分器文本类型
 * 
 * @param score 单个评分器的分数
 * @returns ElementPlus Text 组件的 type 属性值
 */
export function getScorerTextType(score?: number | null): '' | 'danger' | 'warning' | 'success' {
  if (score == null) return ''
  if (score >= 20) return 'danger'
  if (score >= 10) return 'warning'
  return 'success'
}

/**
 * HTTP 状态码标签类型
 * 
 * @param status HTTP 状态码
 * @returns ElementPlus Tag 组件的 type 属性值
 */
export function getHttpStatusType(status?: number | null): 'success' | 'warning' | 'danger' | 'info' {
  if (!status) return 'info'
  if (status >= 500) return 'danger'
  if (status >= 400) return 'warning'
  if (status >= 300) return 'info'
  if (status >= 200) return 'success'
  return 'info'
}

/**
 * 格式化字节大小
 * 
 * @param bytes 字节数
 * @returns 格式化后的大小字符串
 */
export function formatBytes(bytes?: number | null): string {
  if (bytes == null || bytes === 0) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
}

/**
 * 格式化毫秒时间
 * 
 * @param ms 毫秒数
 * @returns 格式化后的时间字符串
 */
export function formatDuration(ms?: number | null): string {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60000).toFixed(2)}min`
}

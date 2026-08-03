/**
 * 通用格式化工具函数
 *
 * 各模块（情报库、Dashboard、访问日志等）共用同一套格式化逻辑，
 * 请勿在页面文件中重复定义。
 */

/**
 * 字节数转可读字符串
 *
 * @example formatBytes(1536)       // "1.5 KB"
 * @example formatBytes(0)          // "0 B"
 * @example formatBytes(104857600)  // "100.0 MB"
 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (!bytes || bytes <= 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(decimals)} ${sizes[i]}`
}

/**
 * 毫秒转可读时长
 *
 * @example formatDuration(800)    // "800ms"
 * @example formatDuration(1500)   // "1.5s"
 * @example formatDuration(65000)  // "65.0s"
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * 截断文本，超出部分用省略号替代
 *
 * @example shortText('hello world', 5)  // "hello…"
 */
export function shortText(text: string, maxLen = 30): string {
  if (!text) return ''
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text
}

/**
 * 将 ISO 时间字符串格式化为本地可读时间
 *
 * @example formatTime('2024-01-01T08:00:00Z')  // "2024/1/1 16:00:00"
 */
export function formatTime(val: string | null | undefined): string {
  if (!val) return '-'
  const d = new Date(val)
  if (isNaN(d.getTime())) return val
  return d.toLocaleString('zh-CN', { hour12: false })
}

/**
 * 将数字格式化为千分位字符串
 *
 * @example formatNumber(1234567)  // "1,234,567"
 */
export function formatNumber(n: number): string {
  return n?.toLocaleString() ?? '-'
}

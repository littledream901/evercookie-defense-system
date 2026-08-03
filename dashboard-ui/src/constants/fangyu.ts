import type { TagType } from './disposition'

/**
 * 防御系统通用枚举与格式化工具
 */

/** 应用状态 */
export const APP_STATUS_OPTIONS = [
  { label: '启用', value: 'active' },
  { label: '暂停', value: 'paused' },
  { label: '归档', value: 'archived' }
]

/** 应用状态 → 标签色 */
export const APP_STATUS_TAGS: Record<string, TagType> = {
  active: 'success',
  inactive: 'warning',
  paused: 'warning',
  archived: 'info'
}

/** 账号状态 */
export const USER_STATUS_OPTIONS = [
  { label: '正常', value: 'active' },
  { label: '停用', value: 'disabled' },
  { label: '锁定', value: 'locked' }
]

/** 账号状态 → 标签色 */
export const USER_STATUS_TAGS: Record<string, TagType> = {
  active: 'success',
  disabled: 'info',
  locked: 'danger'
}

/** 规则状态（五态生命周期） */
export const RULE_STATUS_TAGS: Record<string, TagType> = {
  draft: 'info',
  shadow: 'primary',
  published: 'success',
  disabled: 'warning',
  archived: 'danger'
}

/** 规则状态中文 */
export const RULE_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  shadow: '影子',
  published: '已发布',
  disabled: '已停用',
  archived: '已归档'
}

/** 规则优先级 */
export const RULE_PRIORITY_OPTIONS = [
  { label: '低 (low)', value: 'low' },
  { label: '普通 (normal)', value: 'normal' },
  { label: '高 (high)', value: 'high' },
  { label: '关键 (critical)', value: 'critical' }
]

/** 威胁情报分类 */
export const THREAT_CATEGORY_OPTIONS = [
  { label: '恶意',       value: 'malicious'           },
  { label: '代理',       value: 'proxy'               },
  { label: 'Tor',        value: 'tor'                 },
  { label: 'VPN',        value: 'vpn'                 },
  { label: '扫描器',     value: 'scanner'             },
  { label: '僵尸网络',   value: 'botnet'              },
  { label: '垃圾邮件',   value: 'spam'                },
  { label: '钓鱼',       value: 'phishing'            },
  { label: 'C2 服务器',  value: 'c2'                  },
  { label: '暴力破解',   value: 'brute_force'         },
  { label: '恶意软件',   value: 'malware'             },
  { label: '漏洞利用',   value: 'exploit'             },
  { label: '撞库攻击',   value: 'credential_stuffing' }
]

/** 威胁情报严重度 */
export const THREAT_SEVERITY_OPTIONS = [
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' },
  { label: '严重', value: 'critical' }
]

/** 严重度 → 标签色 */
export const THREAT_SEVERITY_TAGS: Record<string, TagType> = {
  low: 'info',
  medium: 'primary',
  high: 'warning',
  critical: 'danger'
}

/** 威胁情报来源 */
export const THREAT_SOURCE_OPTIONS = [
  { label: '手工录入', value: 'manual' },
  { label: '情报源', value: 'feed' },
  { label: '自动识别', value: 'auto' }
]

/** 设备类型（日志筛选用） */
export const DEVICE_TYPE_OPTIONS = [
  { label: '桌面', value: 'desktop' },
  { label: '移动', value: 'mobile' },
  { label: '平板', value: 'tablet' },
  { label: '机器人', value: 'bot' },
  { label: '未知', value: 'unknown' }
]

/** 网络类型 → 标签色 */
export const CONNECTION_TYPE_TAGS: Record<string, TagType> = {
  datacenter: 'warning',
  mobile: 'primary',
  residential: 'success'
}

/** 频控封禁维度 */
export const BAN_DIMENSION_OPTIONS = [
  { label: 'IP', value: 'ip' },
  { label: '设备指纹', value: 'fingerprint' }
]

/**
 * 按 HTTP 状态码分级着色
 */
export function httpStatusTag(code?: number | null): TagType {
  if (!code) return 'info'
  if (code < 300) return 'success'
  if (code < 400) return 'primary'
  if (code < 500) return 'warning'
  return 'danger'
}

/**
 * 秒数格式化为可读时长
 */
export function formatSeconds(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} 小时`
  return `${(seconds / 86400).toFixed(1)} 天`
}

/**
 * 取最近 N 小时的时间区间（ISO 字符串，UTC）
 */
export function recentRange(hours = 24): { start: string; end: string } {
  const end = new Date()
  const start = new Date(end.getTime() - hours * 3600 * 1000)
  return { start: start.toISOString(), end: end.toISOString() }
}

/**
 * 把 Date 格式化为本地时间字符串 `YYYY-MM-DDTHH:mm:ss`
 *
 * ElDatePicker 的 valueFormat 用的是本地时间，不能直接拿 toISOString()（UTC）填进去，
 * 否则界面显示的时间会与实际查询区间相差一个时区偏移。
 */
export function toLocalDateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

/**
 * 取最近 N 小时的本地时间区间，供 ElDatePicker 的 datetimerange 直接绑定
 */
export function recentLocalRange(hours = 24): [string, string] {
  const end = new Date()
  const start = new Date(end.getTime() - hours * 3600 * 1000)
  return [toLocalDateTime(start), toLocalDateTime(end)]
}

/**
 * 剔除空值参数
 *
 * 空字符串、null、undefined 会被后端当作有效筛选条件，必须在发请求前清掉。
 */
export function pruneParams<T extends Record<string, any>>(params: T): Partial<T> {
  const result: Record<string, any> = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value === '' || value === null || value === undefined) return
    if (Array.isArray(value) && value.length === 0) return
    result[key] = value
  })
  return result as Partial<T>
}

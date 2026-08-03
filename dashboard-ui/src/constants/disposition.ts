/**
 * 处置动作定义
 *
 * 处置采用三层正交模型：裁决（为什么）+ 机制（怎么做）+ 目标（去哪）。
 * 规则模块与访问日志模块共用本文件，因此放在 constants 共享层。
 */

/** Element Plus 标签类型 */
export type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

export interface OptionItem {
  label: string
  value: string
  desc?: string
}

/** 裁决：为什么这么处置 */
export const VERDICT_OPTIONS: OptionItem[] = [
  { label: '可信（trusted）', value: 'trusted', desc: '判定为正常访客' },
  { label: '可疑（suspect）', value: 'suspect', desc: '存在风险信号，需干预但不确定恶意' },
  { label: '恶意（hostile）', value: 'hostile', desc: '判定为攻击或自动化流量' }
]

/** 机制：具体怎么做 */
export const MECHANISM_OPTIONS: OptionItem[] = [
  { label: '放行（pass）', value: 'pass', desc: '不做任何干预' },
  { label: '投放替代内容（serve_alt）', value: 'serve_alt', desc: '返回替代页面，不暴露识别结果' },
  { label: '跳转（redirect）', value: 'redirect', desc: '301/302 跳转到指定地址' },
  { label: '人机挑战（challenge）', value: 'challenge', desc: '要求通过验证后继续' },
  { label: '拒绝（deny）', value: 'deny', desc: '返回 403' },
  { label: '假装不存在（not_found）', value: 'not_found', desc: '返回 404，静默阻断' }
]

/** 目标类型：流量去哪 */
export const TARGET_KIND_OPTIONS: OptionItem[] = [
  { label: '原始目标（origin）', value: 'origin' },
  { label: '指定单一URL（url_single）', value: 'url' },
  { label: '轮询地址池（url_pool）', value: 'url_pool', desc: '多地址按策略分摊' },
  { label: '页面资源（page_resource）', value: 'page_resource' },
  { label: '仅状态码（status_only）', value: 'status_only' }
]

/**
 * 轮询策略
 *
 * hash 与 round_robin 的区别值得留意：运维选「轮询」时脑子里想的往往是严格
 * 轮转，而 hash 是按 request_id 哈希取模的近似均匀分布，短时间内可能倾斜。
 * 需要严格均匀就选 round_robin（代价是每次决策多一次 Redis 写）。
 */
export const ROTATION_STRATEGY_OPTIONS: OptionItem[] = [
  { label: '哈希分摊（hash）', value: 'hash', desc: '无状态，按请求近似均匀分布' },
  { label: '权重分配（weighted）', value: 'weighted', desc: '按权重比例分流，用于灰度放量' },
  { label: '访客粘性（sticky）', value: 'sticky', desc: '同一访客固定地址，牺牲分摊性换会话连续性' },
  { label: '严格轮转（round_robin）', value: 'round_robin', desc: '严格均匀，需 Redis 计数器' },
  { label: '主备容灾（failover）', value: 'failover', desc: '按顺序优先，健康检查失败才切换' }
]

/** 轮询策略 → 标签色 */
export const ROTATION_STRATEGY_TAGS: Record<string, TagType> = {
  hash: 'info',
  weighted: 'primary',
  sticky: 'warning',
  round_robin: 'success',
  failover: 'danger'
}

/** 挑战类型 */
export const CHALLENGE_KIND_OPTIONS: OptionItem[] = [
  { label: '图形验证码', value: 'captcha' },
  { label: 'JS 挑战（轻量）', value: 'js' }
]

/** 裁决 → 标签色 */
export const VERDICT_TAGS: Record<string, TagType> = {
  trusted: 'success',
  suspect: 'warning',
  hostile: 'danger'
}

/** 机制 → 标签色 */
export const MECHANISM_TAGS: Record<string, TagType> = {
  pass: 'success',
  serve_alt: 'info',
  redirect: 'info',
  challenge: 'warning',
  deny: 'danger',
  not_found: 'danger'
}

/** 决策来源，顺序体现决策流水线阶段 */
export const DECIDED_BY_LABELS: Record<string, string> = {
  decision_rule: '决策规则',
  group_no_match: '白名单未命中',
  threat_intel: '威胁情报',
  security: '安全检查',
  scoring: '风险评分',
  hybrid_layer: '混合层',
  app_default: '应用默认',
  system_default: '系统兜底'
}

/** 机制 → 默认状态码，与后端 `_MECHANISM_STATUS` 保持一致 */
export const MECHANISM_STATUS: Record<string, number> = {
  pass: 200,
  serve_alt: 200,
  redirect: 302,
  challenge: 403,
  deny: 403,
  not_found: 404
}

/** 必须填写 URL 的机制 */
export const URL_REQUIRED_MECHANISMS = ['redirect']

/** 必须填写 URL 的目标类型 */
export const URL_REQUIRED_TARGET_KINDS = ['url', 'page_resource']

/** 创建默认处置对象（评分配置用，含 verdict） */
export function createDisposition(): Api.Fangyu.Disposition {
  return {
    verdict: 'trusted',
    mechanism: 'pass',
    target: { kind: 'origin', url: null, urls: null, rotation: null, httpStatus: null },
    challengeKind: null,
    ttlSeconds: 300
  }
}

/** 创建决策规则处置对象（无 verdict） */
export function createDecisionDisposition(): Api.Fangyu.DecisionDisposition {
  return {
    mechanism: 'pass',
    target: { kind: 'origin', url: null, urls: null, rotation: null, httpStatus: null },
    challengeKind: null,
    ttlSeconds: 300
  }
}

/** 创建默认轮询配置，切换到 url_pool 时用 */
export function createRotation(): Api.Fangyu.Rotation {
  return {
    strategy: 'hash',
    entries: [{ url: '', weight: 1, enabled: true, dailyQuota: null, hourlyQuota: null }]
  }
}

/** 创建地址池条目 */
export function createPoolEntry(): Api.Fangyu.PoolEntry {
  return { url: '', weight: 1, enabled: true, dailyQuota: null, hourlyQuota: null }
}

/** 常用预设，避免每次都要配三层 */
export const DISPOSITION_PRESETS: Array<{
  label: string
  value: string
  build: () => Api.Fangyu.Disposition
}> = [
  { label: '放行', value: 'allow', build: () => createDisposition() },
  {
    label: '放行并观察',
    value: 'observe',
    build: () => ({ ...createDisposition(), verdict: 'suspect', ttlSeconds: 300 })
  },
  {
    label: '图形验证码',
    value: 'captcha',
    build: () => ({
      ...createDisposition(),
      verdict: 'suspect',
      mechanism: 'challenge',
      challengeKind: 'captcha'
    })
  },
  {
    label: '拒绝（403）',
    value: 'deny',
    build: () => ({
      ...createDisposition(),
      verdict: 'hostile',
      mechanism: 'deny',
      ttlSeconds: 900
    })
  },
  {
    label: '静默阻断（404）',
    value: 'not_found',
    build: () => ({
      ...createDisposition(),
      verdict: 'hostile',
      mechanism: 'not_found',
      ttlSeconds: 900
    })
  }
]

/**
 * 可校验的处置对象
 *
 * 用结构类型而非 `Disposition | DecisionDisposition` 联合：校验逻辑一条都不涉及
 * `verdict`，用联合类型会让调用方误以为 verdict 参与校验。规则页传的是无 verdict
 * 的 DecisionDisposition，评分页传的是完整 Disposition，两者都满足此结构。
 */
export interface ValidatableDisposition {
  mechanism: string
  target?: {
    kind?: string
    url?: string | null
    urls?: string[] | null
    rotation?: { strategy?: string; entries?: Array<{ url?: string; weight?: number; enabled?: boolean }> } | null
  } | null
  challengeKind?: string | null
}

/**
 * 该 target 是否已提供任一可用地址
 *
 * 三种来源都算：新版 rotation.entries、旧版 urls、单地址 url。只查 url 会让
 * 「只配了地址池」的合法配置被误判为缺地址——这正是修复前的表现。
 */
function hasAnyTargetUrl(target?: ValidatableDisposition['target']): boolean {
  if (!target) return false
  if (target.rotation?.entries?.some((e) => e.url?.trim())) return true
  if (target.urls?.some((u) => u?.trim())) return true
  return !!target.url?.trim()
}

/**
 * 校验处置配置
 *
 * 五条互斥校验按序返回首个错误，注意第 5 条是反向互斥。
 * 与后端 `disposition.py` 的 `_check_semantics` + `_check_url_required` 对齐，
 * 目的是把错误就地提示在字段旁，而不是等后端抛 ValueError 再弹一个通用报错。
 *
 * @returns 错误文案，校验通过返回 null
 */
export function validateDisposition(d?: ValidatableDisposition | null): string | null {
  if (!d) return '请配置处置动作'
  if (URL_REQUIRED_MECHANISMS.includes(d.mechanism) && !hasAnyTargetUrl(d.target)) {
    return '跳转机制必须填写目标 URL'
  }
  if (d.target?.kind && URL_REQUIRED_TARGET_KINDS.includes(d.target.kind) && !hasAnyTargetUrl(d.target)) {
    return d.target.kind === 'page_resource'
      ? '目标类型为页面资源时必须选择资源'
      : '该目标类型必须填写 URL'
  }
  if (d.target?.kind === 'url_pool' && !hasAnyTargetUrl(d.target)) {
    return '轮询地址池至少需要一个地址'
  }
  if (d.mechanism === 'challenge' && !d.challengeKind) {
    return '人机挑战必须选择挑战类型'
  }
  if (d.mechanism !== 'challenge' && d.challengeKind) {
    return '挑战类型仅在人机挑战时可用'
  }
  return null
}

/**
 * 机制 → 允许的目标类型
 *
 * 后端当前**不校验**机制与目标类型的一致性（审计项 FY-DISP-016），前端先按
 * 语义收窄可选项，避免运维配出 `deny + kind=url` 这类自相矛盾的组合。
 */
export const MECHANISM_TARGET_KINDS: Record<string, string[]> = {
  pass: ['origin'],
  serve_alt: ['page_resource'],
  redirect: ['url', 'url_pool'],
  challenge: ['origin'],
  deny: ['origin', 'status_only'],
  not_found: ['origin', 'status_only']
}

/** 该机制下可选的目标类型选项，未知机制回退为全部 */
export function targetKindOptionsFor(mechanism: string): OptionItem[] {
  const allowed = MECHANISM_TARGET_KINDS[mechanism]
  if (!allowed) return TARGET_KIND_OPTIONS
  return TARGET_KIND_OPTIONS.filter((o) => allowed.includes(o.value))
}

/** 该机制的默认目标类型，用于切换机制时自动纠正 */
export function defaultTargetKindFor(mechanism: string): string {
  return MECHANISM_TARGET_KINDS[mechanism]?.[0] ?? 'origin'
}

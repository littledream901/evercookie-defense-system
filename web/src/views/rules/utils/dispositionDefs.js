export const VERDICT_OPTIONS = [
  { label: '可信（trusted）', value: 'trusted', desc: '判定为正常访客' },
  { label: '可疑（suspect）', value: 'suspect', desc: '存在风险信号，需干预但不确定恶意' },
  { label: '恶意（hostile）', value: 'hostile', desc: '判定为攻击或自动化流量' },
]

export const MECHANISM_OPTIONS = [
  { label: '放行（pass）', value: 'pass', desc: '不做任何干预' },
  { label: '投放替代内容（serve_alt）', value: 'serve_alt', desc: '返回替代页面，不暴露识别结果' },
  { label: '跳转（redirect）', value: 'redirect', desc: '301/302 跳转到指定地址' },
  { label: '人机挑战（challenge）', value: 'challenge', desc: '要求通过验证后继续' },
  { label: '拒绝（deny）', value: 'deny', desc: '返回 403' },
  { label: '假装不存在（not_found）', value: 'not_found', desc: '返回 404，静默阻断' },
]

export const TARGET_KIND_OPTIONS = [
  { label: '原始目标（origin）', value: 'origin' },
  { label: '指定 URL（url）', value: 'url' },
  { label: '页面资源（page_resource）', value: 'page_resource' },
  { label: '仅状态码（status_only）', value: 'status_only' },
]

export const CHALLENGE_KIND_OPTIONS = [
  { label: '图形验证码', value: 'captcha' },
  { label: 'JS 挑战（轻量）', value: 'js' },
]

export const VERDICT_TAGS = { trusted: 'success', suspect: 'warning', hostile: 'error' }

export const MECHANISM_TAGS = {
  pass: 'success',
  serve_alt: 'info',
  redirect: 'info',
  challenge: 'warning',
  deny: 'error',
  not_found: 'error',
}

export const DECIDED_BY_LABELS = {
  decision_rule: '决策规则',
  group_no_match: '白名单未命中',
  threat_intel: '威胁情报',
  security: '安全检查',
  scoring: '风险评分',
  app_default: '应用默认',
  system_default: '系统兜底',
}

// 机制 → 默认状态码，与后端 _MECHANISM_STATUS 保持一致
export const MECHANISM_STATUS = {
  pass: 200,
  serve_alt: 200,
  redirect: 302,
  challenge: 403,
  deny: 403,
  not_found: 404,
}

export const URL_REQUIRED_MECHANISMS = ['redirect']
export const URL_REQUIRED_TARGET_KINDS = ['url', 'page_resource']

export function createDisposition() {
  return {
    verdict: 'trusted',
    mechanism: 'pass',
    target: { kind: 'origin', url: null, httpStatus: null },
    challengeKind: null,
    ttlSeconds: 300,
  }
}

// 常用预设，避免每次都要配三层
export const DISPOSITION_PRESETS = [
  { label: '放行', value: 'allow', build: () => createDisposition() },
  {
    label: '放行并观察',
    value: 'observe',
    build: () => ({ ...createDisposition(), verdict: 'suspect', ttlSeconds: 300 }),
  },
  {
    label: '图形验证码',
    value: 'captcha',
    build: () => ({
      ...createDisposition(),
      verdict: 'suspect',
      mechanism: 'challenge',
      challengeKind: 'captcha',
    }),
  },
  {
    label: '拒绝（403）',
    value: 'deny',
    build: () => ({
      ...createDisposition(),
      verdict: 'hostile',
      mechanism: 'deny',
      ttlSeconds: 900,
    }),
  },
  {
    label: '静默阻断（404）',
    value: 'not_found',
    build: () => ({
      ...createDisposition(),
      verdict: 'hostile',
      mechanism: 'not_found',
      ttlSeconds: 900,
    }),
  },
]

export function validateDisposition(d) {
  if (!d) return '请配置处置动作'
  if (URL_REQUIRED_MECHANISMS.includes(d.mechanism) && !d.target?.url) {
    return '跳转机制必须填写目标 URL'
  }
  if (URL_REQUIRED_TARGET_KINDS.includes(d.target?.kind) && !d.target?.url) {
    return '该目标类型必须填写 URL'
  }
  if (d.mechanism === 'challenge' && !d.challengeKind) {
    return '人机挑战必须选择挑战类型'
  }
  if (d.mechanism !== 'challenge' && d.challengeKind) {
    return '挑战类型仅在人机挑战时可用'
  }
  return null
}

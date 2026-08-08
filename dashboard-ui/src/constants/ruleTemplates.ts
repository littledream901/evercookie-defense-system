/**
 * 规则模板配置
 * 预定义常用规则场景，支持一键应用
 */

export interface RuleCondition {
  field: string
  operator: string
  value: any
}

export interface RuleDisposition {
  mechanism: 'allow' | 'challenge' | 'block' | 'serve_alt' | 'redirect' | 'rate_limit'
  ttlSeconds: number
  challengeKind?: 'js_challenge' | 'captcha' | 'slider'
  target?: {
    kind: string
    url?: string
    statusCode?: number
  }
}

export interface RuleTemplate {
  id: string
  name: string
  category: string
  description: string
  icon?: string
  priority: 'critical' | 'high' | 'normal' | 'low'
  matchAll: boolean
  conditions: RuleCondition[]
  onMatch: RuleDisposition
  onMiss: RuleDisposition
  tags?: string[]
  frequency?: 'high' | 'medium' | 'low'
  riskLevel?: 'low' | 'medium' | 'high'
}

// ========== 规则模板库 ==========

export const RULE_TEMPLATES: RuleTemplate[] = [
  // ========== 爬虫管理 ==========
  {
    id: 'allow-search-engine-crawlers',
    name: '放行搜索引擎爬虫',
    category: '爬虫管理',
    description: '允许 Google、Bing、百度等主流搜索引擎爬虫访问，保障 SEO',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'ua.crawler_category', operator: 'eq', value: 'search_engine' }
    ],
    onMatch: { mechanism: 'allow', ttlSeconds: 3600 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', 'SEO', '白名单'],
    frequency: 'high',
    riskLevel: 'low'
  },
  {
    id: 'block-ai-crawlers',
    name: '拦截 AI 爬虫',
    category: '爬虫管理',
    description: '阻止 GPTBot、ClaudeBot 等 AI 训练爬虫抓取内容',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'ua.crawler_category', operator: 'eq', value: 'ai_crawler' }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 86400, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', 'AI', '拦截'],
    frequency: 'high',
    riskLevel: 'low'
  },
  {
    id: 'challenge-unknown-crawlers',
    name: '挑战未知爬虫',
    category: '爬虫管理',
    description: '对无法识别的爬虫进行 JS 挑战验证',
    priority: 'normal',
    matchAll: true,
    conditions: [
      { field: 'ua.is_crawler', operator: 'eq', value: true },
      { field: 'ua.crawler_name', operator: 'eq', value: '__NULL__' }
    ],
    onMatch: { mechanism: 'challenge', ttlSeconds: 1800, challengeKind: 'js_challenge' },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', '挑战', '未知'],
    frequency: 'medium',
    riskLevel: 'medium'
  },
  {
    id: 'allow-googlebot',
    name: '放行 Googlebot（核心搜索）',
    category: '爬虫管理',
    description: 'Google 核心搜索爬虫专属规则，确保网站被正确索引，提升 SEO 排名',
    priority: 'critical',
    matchAll: true,
    conditions: [
      { field: 'ua.crawler_vendor', operator: 'eq', value: 'google' },
      { field: 'ua.crawler_name', operator: 'eq', value: 'googlebot' }
    ],
    onMatch: { mechanism: 'allow', ttlSeconds: 7200 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', 'Google', 'SEO', '白名单'],
    frequency: 'high',
    riskLevel: 'low'
  },
  {
    id: 'allow-google-adsbot',
    name: '放行 Google AdsBot（广告质量）',
    category: '爬虫管理',
    description: 'Google Ads 广告质量检查爬虫，用于评估广告着陆页质量和相关性',
    priority: 'high',
    matchAll: true,
    conditions: [
      { field: 'ua.crawler_vendor', operator: 'eq', value: 'google' },
      { field: 'ua.crawler_name', operator: 'in', value: ['adsbot-google', 'adsbot-google-mobile'] }
    ],
    onMatch: { mechanism: 'allow', ttlSeconds: 7200 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', 'Google', '广告', 'AdsBot'],
    frequency: 'medium',
    riskLevel: 'low'
  },
  {
    id: 'allow-google-image-crawler',
    name: '放行 Google 图片爬虫',
    category: '爬虫管理',
    description: 'Google 图片搜索爬虫，用于索引网站图片资源',
    priority: 'high',
    matchAll: true,
    conditions: [
      { field: 'ua.crawler_vendor', operator: 'eq', value: 'google' },
      { field: 'ua.crawler_name', operator: 'eq', value: 'googlebot-image' }
    ],
    onMatch: { mechanism: 'allow', ttlSeconds: 7200 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', 'Google', '图片', 'SEO'],
    frequency: 'medium',
    riskLevel: 'low'
  },
  {
    id: 'allow-google-mobile-crawler',
    name: '放行 Google 移动端爬虫',
    category: '爬虫管理',
    description: 'Google 移动优先索引爬虫，评估移动端页面体验',
    priority: 'critical',
    matchAll: true,
    conditions: [
      { field: 'ua.crawler_vendor', operator: 'eq', value: 'google' },
      { field: 'ua.crawler_name', operator: 'in', value: ['googlebot-mobile', 'googlebot-smartphone'] }
    ],
    onMatch: { mechanism: 'allow', ttlSeconds: 7200 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['爬虫', 'Google', '移动端', 'SEO'],
    frequency: 'high',
    riskLevel: 'low'
  },

  // ========== 地理位置 ==========
  {
    id: 'block-high-risk-countries',
    name: '拦截高风险国家',
    category: '地理位置',
    description: '阻止来自已知高风险国家的访问（需根据业务调整国家列表）',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'ip.country', operator: 'in', value: ['KP', 'IR', 'SY'] }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 3600, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['地理位置', '黑名单', '安全'],
    frequency: 'medium',
    riskLevel: 'high'
  },
  {
    id: 'allow-domestic-only',
    name: '仅允许中国大陆访问',
    category: '地理位置',
    description: '限制仅中国大陆 IP 可访问（适用于内网服务）',
    priority: 'critical',
    matchAll: false,
    conditions: [
      { field: 'ip.country', operator: 'neq', value: 'CN' }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 3600, target: { kind: 'fixed_response', statusCode: 451 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['地理位置', '地域限制', '合规'],
    frequency: 'medium',
    riskLevel: 'medium'
  },

  // ========== 网络安全 ==========
  {
    id: 'block-vpn-datacenter',
    name: '拦截 VPN 和数据中心',
    category: '网络安全',
    description: '阻止通过 VPN、代理、数据中心访问，防止批量注册和欺诈',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'ip.is_vpn', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 7200, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['网络安全', 'VPN', '欺诈'],
    frequency: 'high',
    riskLevel: 'high'
  },
  {
    id: 'challenge-tor-exit-nodes',
    name: '挑战 Tor 出口节点',
    category: '网络安全',
    description: '对 Tor 匿名网络用户进行验证码挑战',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'ip.is_tor', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'challenge', ttlSeconds: 1800, challengeKind: 'captcha' },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['网络安全', 'Tor', '匿名'],
    frequency: 'low',
    riskLevel: 'high'
  },
  {
    id: 'block-hosting-providers',
    name: '拦截云主机 IP',
    category: '网络安全',
    description: '阻止云服务商（AWS、阿里云等）的服务器 IP 访问',
    priority: 'normal',
    matchAll: false,
    conditions: [
      { field: 'ip.is_hosting', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 3600, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['网络安全', '云主机', '托管'],
    frequency: 'medium',
    riskLevel: 'medium'
  },

  // ========== 威胁情报 ==========
  {
    id: 'block-threat-intel-malicious',
    name: '拦截恶意 IP',
    category: '威胁情报',
    description: '阻止威胁情报库中标记为恶意的 IP 地址',
    priority: 'critical',
    matchAll: false,
    conditions: [
      { field: 'threat.is_malicious', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 86400, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['威胁情报', '恶意IP', '安全'],
    frequency: 'high',
    riskLevel: 'high'
  },
  {
    id: 'challenge-threat-intel-suspicious',
    name: '挑战可疑 IP',
    category: '威胁情报',
    description: '对威胁情报库中标记为可疑的 IP 进行 JS 挑战',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'threat.is_suspicious', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'challenge', ttlSeconds: 3600, challengeKind: 'js_challenge' },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['威胁情报', '可疑IP', '挑战'],
    frequency: 'medium',
    riskLevel: 'medium'
  },

  // ========== 风险评分 ==========
  {
    id: 'block-high-risk-score',
    name: '拦截高风险请求',
    category: '风险评分',
    description: '阻止风险评分 >= 80 的请求（综合评估多维度指标）',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'risk.total_score', operator: 'gte', value: 80 }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 1800, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['风险评分', '高风险', '综合'],
    frequency: 'high',
    riskLevel: 'high'
  },
  {
    id: 'challenge-medium-risk-score',
    name: '挑战中风险请求',
    category: '风险评分',
    description: '对风险评分 50-79 的请求进行滑块验证',
    priority: 'normal',
    matchAll: true,
    conditions: [
      { field: 'risk.total_score', operator: 'gte', value: 50 },
      { field: 'risk.total_score', operator: 'lt', value: 80 }
    ],
    onMatch: { mechanism: 'challenge', ttlSeconds: 1800, challengeKind: 'slider' },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['风险评分', '中风险', '验证'],
    frequency: 'high',
    riskLevel: 'medium'
  },

  // ========== 设备指纹 ==========
  {
    id: 'block-bot-ua',
    name: '拦截机器人 UA',
    category: '设备指纹',
    description: '阻止 User-Agent 中包含 bot/crawler/spider 等关键词的请求',
    priority: 'normal',
    matchAll: false,
    conditions: [
      { field: 'ua.is_bot', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 3600, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['设备指纹', 'UA', '机器人'],
    frequency: 'high',
    riskLevel: 'low'
  },
  {
    id: 'challenge-headless-browser',
    name: '挑战无头浏览器',
    category: '设备指纹',
    description: '对检测到的 Selenium、Puppeteer 等自动化工具进行验证',
    priority: 'normal',
    matchAll: false,
    conditions: [
      { field: 'ua.is_headless', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'challenge', ttlSeconds: 1800, challengeKind: 'js_challenge' },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['设备指纹', '无头浏览器', '自动化'],
    frequency: 'medium',
    riskLevel: 'medium'
  },

  // ========== 行为分析 ==========
  {
    id: 'rate-limit-high-frequency',
    name: '限流高频访问',
    category: '行为分析',
    description: '对 1 分钟内请求超过 100 次的 IP 进行限流',
    priority: 'high',
    matchAll: false,
    conditions: [
      { field: 'behavior.request_count_1m', operator: 'gt', value: 100 }
    ],
    onMatch: { mechanism: 'rate_limit', ttlSeconds: 60 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['行为分析', '限流', '高频'],
    frequency: 'high',
    riskLevel: 'medium'
  },
  {
    id: 'challenge-abnormal-path-traversal',
    name: '挑战异常路径遍历',
    category: '行为分析',
    description: '检测短时间内访问大量不同路径的行为',
    priority: 'normal',
    matchAll: false,
    conditions: [
      { field: 'behavior.unique_paths_10m', operator: 'gt', value: 50 }
    ],
    onMatch: { mechanism: 'challenge', ttlSeconds: 1800, challengeKind: 'captcha' },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['行为分析', '路径遍历', '爬取'],
    frequency: 'medium',
    riskLevel: 'medium'
  },

  // ========== 请求属性 ==========
  {
    id: 'block-missing-referer',
    name: '拦截无 Referer 请求',
    category: '请求属性',
    description: '阻止缺少 Referer 头的请求（可能是脚本直接调用）',
    priority: 'low',
    matchAll: false,
    conditions: [
      { field: 'request.referer', operator: 'eq', value: '__NULL__' }
    ],
    onMatch: { mechanism: 'block', ttlSeconds: 600, target: { kind: 'fixed_response', statusCode: 403 } },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['请求属性', 'Referer', '防盗链'],
    frequency: 'low',
    riskLevel: 'low'
  },
  {
    id: 'allow-api-key-auth',
    name: '放行 API Key 认证',
    category: '请求属性',
    description: '携带有效 API Key 的请求直接放行',
    priority: 'critical',
    matchAll: false,
    conditions: [
      { field: 'request.has_valid_api_key', operator: 'eq', value: true }
    ],
    onMatch: { mechanism: 'allow', ttlSeconds: 3600 },
    onMiss: { mechanism: 'allow', ttlSeconds: 0 },
    tags: ['请求属性', 'API Key', '认证'],
    frequency: 'high',
    riskLevel: 'low'
  }
]

// ========== 工具函数 ==========

/**
 * 获取所有模板分类
 */
export function getTemplateCategories(): string[] {
  const categories = new Set(RULE_TEMPLATES.map(t => t.category))
  return Array.from(categories)
}

/**
 * 按分类获取模板
 */
export function getTemplatesByCategory(category: string): RuleTemplate[] {
  return RULE_TEMPLATES.filter(t => t.category === category)
}

/**
 * 按ID获取模板
 */
export function getTemplateById(id: string): RuleTemplate | undefined {
  return RULE_TEMPLATES.find(t => t.id === id)
}

/**
 * 搜索模板
 */
export function searchTemplates(keyword: string): RuleTemplate[] {
  const kw = keyword.toLowerCase().trim()
  if (!kw) return RULE_TEMPLATES

  return RULE_TEMPLATES.filter(t => {
    return (
      t.name.toLowerCase().includes(kw) ||
      t.description.toLowerCase().includes(kw) ||
      t.category.toLowerCase().includes(kw) ||
      t.tags?.some(tag => tag.toLowerCase().includes(kw))
    )
  })
}

/**
 * 获取常用模板（高频使用）
 */
export function getFrequentTemplates(): RuleTemplate[] {
  return RULE_TEMPLATES.filter(t => t.frequency === 'high')
}

/**
 * 获取高风险模板
 */
export function getHighRiskTemplates(): RuleTemplate[] {
  return RULE_TEMPLATES.filter(t => t.riskLevel === 'high')
}

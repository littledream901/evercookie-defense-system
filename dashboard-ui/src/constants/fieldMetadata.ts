/**
 * 字段元数据定义
 * 用于规则条件构建器的智能提示和验证
 */

export interface FieldOption {
  value: any
  label: string
  desc?: string
  icon?: string
}

export interface FieldMetadata {
  label: string
  category: string
  type: 'string' | 'number' | 'bool' | 'enum'
  hint: string
  placeholder?: string
  options?: FieldOption[]
  examples?: any[]
  range?: { min: number; max: number }
  unit?: string
  frequency?: 'high' | 'medium' | 'low'
  caseSensitive?: boolean
  nullable?: boolean
  learnMore?: string
  recommendations?: Array<{
    range?: string
    value?: any
    label: string
    color: 'success' | 'warning' | 'danger' | 'info'
    desc: string
  }>
  commonValues?: Array<{
    value: any
    label: string
    count?: number
  }>
  riskLevel?: 'low' | 'medium' | 'high'
}

// ========== IP 画像字段 ==========
const IP_FIELDS: Record<string, FieldMetadata> = {
  'ip.country': {
    label: 'IP 国家',
    category: 'IP画像',
    type: 'enum',
    hint: '访问者 IP 地址所在国家（ISO 3166-1 alpha-2 代码）',
    placeholder: '选择国家',
    options: [
      { value: 'CN', label: '中国', desc: '中国大陆' },
      { value: 'HK', label: '香港', desc: '中国香港特别行政区' },
      { value: 'MO', label: '澳门', desc: '中国澳门特别行政区' },
      { value: 'TW', label: '台湾', desc: '中国台湾' },
      { value: 'US', label: '美国', desc: '美利坚合众国' },
      { value: 'JP', label: '日本', desc: '日本国' },
      { value: 'KR', label: '韩国', desc: '大韩民国' },
      { value: 'SG', label: '新加坡', desc: '新加坡共和国' },
      { value: 'GB', label: '英国', desc: '大不列颠及北爱尔兰联合王国' },
      { value: 'DE', label: '德国', desc: '德意志联邦共和国' },
      { value: 'FR', label: '法国', desc: '法兰西共和国' },
      { value: 'RU', label: '俄罗斯', desc: '俄罗斯联邦' },
      { value: 'IN', label: '印度', desc: '印度共和国' },
      { value: 'AU', label: '澳大利亚', desc: '澳大利亚联邦' },
      { value: 'CA', label: '加拿大', desc: '加拿大' }
    ],
    examples: ['CN', 'US', 'JP'],
    frequency: 'high',
    caseSensitive: false,
    nullable: true
  },

  'ip.continent': {
    label: 'IP 大洲',
    category: 'IP画像',
    type: 'enum',
    hint: '访问者 IP 地址所在大洲',
    placeholder: '选择大洲',
    options: [
      { value: 'AS', label: '亚洲', desc: 'Asia' },
      { value: 'EU', label: '欧洲', desc: 'Europe' },
      { value: 'NA', label: '北美洲', desc: 'North America' },
      { value: 'SA', label: '南美洲', desc: 'South America' },
      { value: 'AF', label: '非洲', desc: 'Africa' },
      { value: 'OC', label: '大洋洲', desc: 'Oceania' },
      { value: 'AN', label: '南极洲', desc: 'Antarctica' }
    ],
    examples: ['AS', 'EU', 'NA'],
    frequency: 'medium',
    nullable: true
  },

  'ip.city': {
    label: 'IP 城市',
    category: 'IP画像',
    type: 'string',
    hint: 'IP 地址所在城市名称',
    placeholder: '如：Beijing, Shanghai, New York',
    examples: ['Beijing', 'Shanghai', 'Shenzhen', 'New York', 'London'],
    frequency: 'low',
    caseSensitive: false,
    nullable: true
  },

  'ip.asn': {
    label: 'ASN 自治系统号',
    category: 'IP画像',
    type: 'number',
    hint: 'IP 所属的网络运营商自治系统编号',
    placeholder: '如：4134（中国电信）',
    examples: [4134, 4837, 13335],
    frequency: 'medium',
    nullable: true,
    learnMore: 'https://zh.wikipedia.org/wiki/自治系统',
    commonValues: [
      { value: 4134, label: '中国电信', count: 12000 },
      { value: 4837, label: '中国联通', count: 8000 },
      { value: 4538, label: '中国教育网', count: 5000 },
      { value: 13335, label: 'Cloudflare', count: 4500 },
      { value: 8075, label: 'Microsoft Azure', count: 3000 },
      { value: 16509, label: 'Amazon AWS', count: 2800 }
    ]
  },

  'ip.asnOrg': {
    label: 'ASN 组织名称',
    category: 'IP画像',
    type: 'string',
    hint: 'ASN 所属的组织或运营商名称',
    placeholder: '如：China Telecom, Cloudflare',
    examples: ['China Telecom', 'China Unicom', 'Cloudflare', 'Amazon'],
    frequency: 'medium',
    caseSensitive: false,
    nullable: true
  },

  'ip.isVpn': {
    label: 'VPN 检测',
    category: '网络安全',
    type: 'bool',
    hint: '是否检测到使用 VPN 或虚拟专用网络',
    options: [
      { value: true, label: '是', desc: '检测到 VPN 流量特征' },
      { value: false, label: '否', desc: '未检测到 VPN' }
    ],
    examples: [true, false],
    frequency: 'high',
    riskLevel: 'medium'
  },

  'ip.isProxy': {
    label: '代理检测',
    category: '网络安全',
    type: 'bool',
    hint: '是否检测到使用代理服务器',
    options: [
      { value: true, label: '是', desc: '检测到代理特征' },
      { value: false, label: '否', desc: '未检测到代理' }
    ],
    examples: [true, false],
    frequency: 'high',
    riskLevel: 'medium'
  },

  'ip.isTor': {
    label: 'Tor 网络检测',
    category: '网络安全',
    type: 'bool',
    hint: '是否来自 Tor 匿名网络出口节点',
    options: [
      { value: true, label: '是', desc: 'Tor 出口节点' },
      { value: false, label: '否', desc: '非 Tor 网络' }
    ],
    examples: [true, false],
    frequency: 'medium',
    riskLevel: 'high'
  },

  'ip.isDatacenter': {
    label: '数据中心 IP',
    category: '网络安全',
    type: 'bool',
    hint: '是否为云厂商或 IDC 机房 IP',
    options: [
      { value: true, label: '是', desc: '数据中心 IP 段' },
      { value: false, label: '否', desc: '家庭或企业宽带' }
    ],
    examples: [true, false],
    frequency: 'high',
    riskLevel: 'medium'
  },

  'ip.isHosting': {
    label: '托管 IP',
    category: '网络安全',
    type: 'bool',
    hint: '是否为托管服务商 IP',
    options: [
      { value: true, label: '是', desc: '托管服务 IP' },
      { value: false, label: '否', desc: '非托管 IP' }
    ],
    examples: [true, false],
    frequency: 'medium',
    riskLevel: 'low'
  }
}

// ========== UA 解析字段 ==========
const UA_FIELDS: Record<string, FieldMetadata> = {
  'ua.is_bot': {
    label: '是否爬虫',
    category: '爬虫识别',
    type: 'bool',
    hint: '是否识别为爬虫或自动化程序',
    options: [
      { value: true, label: '是', desc: '识别为爬虫' },
      { value: false, label: '否', desc: '识别为真实用户' }
    ],
    examples: [true, false],
    frequency: 'high'
  },

  'ua.crawler_name': {
    label: '爬虫名称',
    category: '爬虫识别',
    type: 'enum',
    hint: '具体的爬虫程序名称（如 googlebot、bingbot）',
    placeholder: '选择或输入爬虫名称',
    options: [
      // Google 爬虫系列
      { value: 'googlebot', label: 'Googlebot', desc: 'Google 核心搜索爬虫' },
      { value: 'googlebot-image', label: 'Googlebot-Image', desc: 'Google 图片搜索' },
      { value: 'googlebot-news', label: 'Googlebot-News', desc: 'Google 新闻搜索' },
      { value: 'googlebot-video', label: 'Googlebot-Video', desc: 'Google 视频搜索' },
      { value: 'googlebot-mobile', label: 'Googlebot-Mobile', desc: 'Google 移动端爬虫' },
      { value: 'googlebot-smartphone', label: 'Googlebot-Smartphone', desc: 'Google 智能手机爬虫' },
      { value: 'adsbot-google', label: 'AdsBot-Google', desc: 'Google Ads 广告质量检查' },
      { value: 'adsbot-google-mobile', label: 'AdsBot-Google-Mobile', desc: 'Google Ads 移动端检查' },
      { value: 'mediapartners-google', label: 'Mediapartners-Google', desc: 'Google AdSense 爬虫' },
      { value: 'feedfetcher-google', label: 'FeedFetcher-Google', desc: 'Google RSS/Feed 抓取' },
      { value: 'storebot-google', label: 'Storebot-Google', desc: 'Google 购物爬虫' },
      { value: 'google-inspectiontool', label: 'Google-InspectionTool', desc: 'Search Console 检查工具' },
      { value: 'googleother', label: 'GoogleOther', desc: '其他 Google 服务' },
      
      // Bing 爬虫系列
      { value: 'bingbot', label: 'Bingbot', desc: 'Bing 搜索爬虫' },
      { value: 'adidxbot', label: 'AdIdxBot', desc: 'Bing 广告索引爬虫' },
      { value: 'bingpreview', label: 'BingPreview', desc: 'Bing 页面预览' },
      { value: 'msnbot', label: 'MSNBot', desc: 'MSN 搜索爬虫' },
      
      // 百度爬虫系列
      { value: 'baiduspider', label: 'Baiduspider', desc: '百度搜索爬虫' },
      { value: 'baiduspider-render', label: 'Baiduspider-Render', desc: '百度渲染爬虫' },
      { value: 'baiduspider-image', label: 'Baiduspider-Image', desc: '百度图片爬虫' },
      
      // AI 爬虫
      { value: 'gptbot', label: 'GPTBot', desc: 'OpenAI ChatGPT 爬虫' },
      { value: 'claudebot', label: 'ClaudeBot', desc: 'Anthropic Claude 爬虫' },
      { value: 'ccbot', label: 'CCBot', desc: 'Common Crawl 爬虫' },
      { value: 'google-extended', label: 'Google-Extended', desc: 'Google AI 训练数据爬虫' },
      { value: 'perplexitybot', label: 'PerplexityBot', desc: 'Perplexity AI 爬虫' },
      { value: 'bytespider', label: 'ByteSpider', desc: '字节跳动爬虫' },
      
      // 其他常见爬虫
      { value: 'yandexbot', label: 'YandexBot', desc: 'Yandex 搜索爬虫' },
      { value: 'applebot', label: 'Applebot', desc: 'Apple 搜索爬虫' },
      { value: 'facebookexternalhit', label: 'FacebookExternalHit', desc: 'Facebook 预览爬虫' },
      { value: 'twitterbot', label: 'Twitterbot', desc: 'Twitter 卡片爬虫' },
      { value: 'linkedinbot', label: 'LinkedInBot', desc: 'LinkedIn 爬虫' },
      { value: 'slackbot', label: 'Slackbot', desc: 'Slack 链接预览' },
      { value: 'discordbot', label: 'Discordbot', desc: 'Discord 预览爬虫' },
      
      // SEO 工具
      { value: 'ahrefsbot', label: 'AhrefsBot', desc: 'Ahrefs SEO 爬虫' },
      { value: 'semrushbot', label: 'SemrushBot', desc: 'Semrush SEO 爬虫' },
      { value: 'mj12bot', label: 'MJ12bot', desc: 'Majestic SEO 爬虫' },
      
      // 监控工具
      { value: 'uptimerobot', label: 'UptimeRobot', desc: 'UptimeRobot 监控' },
      { value: 'pingdom', label: 'Pingdom', desc: 'Pingdom 监控' }
    ],
    examples: ['googlebot', 'bingbot', 'gptbot', 'ahrefsbot'],
    frequency: 'high',
    caseSensitive: false,
    nullable: true
  },

  'ua.crawler_category': {
    label: '爬虫类别',
    category: '爬虫识别',
    type: 'enum',
    hint: '爬虫的功能分类',
    placeholder: '选择爬虫类别',
    options: [
      { value: 'search_engine', label: '搜索引擎', desc: 'Google/Bing/百度等' },
      { value: 'social', label: '社交媒体', desc: '微信/Twitter/Facebook等' },
      { value: 'ai_crawler', label: 'AI 爬虫', desc: 'GPTBot/ClaudeBot/CCBot等' },
      { value: 'seo', label: 'SEO 工具', desc: 'Ahrefs/Semrush/Majestic等' },
      { value: 'monitoring', label: '监控探测', desc: 'UptimeRobot/Pingdom等' },
      { value: 'security', label: '安全扫描器', desc: 'sqlmap/nikto/nuclei等' },
      { value: 'library', label: '脚本库', desc: 'curl/wget/requests等' },
      { value: 'feed', label: 'RSS 订阅', desc: 'Feedly/Inoreader等' },
      { value: 'archive', label: '网页存档', desc: 'Internet Archive等' },
      { value: 'other', label: '其他爬虫', desc: '未分类的爬虫' }
    ],
    examples: ['search_engine', 'ai_crawler', 'security'],
    frequency: 'high',
    nullable: true
  },

  'ua.crawler_vendor': {
    label: '爬虫厂商',
    category: '爬虫识别',
    type: 'enum',
    hint: '爬虫所属的厂商或组织',
    placeholder: '选择爬虫厂商',
    options: [
      { value: 'google', label: 'Google', desc: 'Google 搜索引擎' },
      { value: 'bing', label: 'Bing', desc: 'Microsoft Bing' },
      { value: 'baidu', label: 'Baidu', desc: '百度搜索' },
      { value: 'openai', label: 'OpenAI', desc: 'GPTBot' },
      { value: 'anthropic', label: 'Anthropic', desc: 'Claude-Web' },
      { value: 'ahrefs', label: 'Ahrefs', desc: 'Ahrefs SEO 工具' },
      { value: 'semrush', label: 'Semrush', desc: 'Semrush SEO 工具' },
      { value: 'yandex', label: 'Yandex', desc: 'Yandex 搜索引擎' },
      { value: 'meta', label: 'Meta', desc: 'Facebook/Instagram' }
    ],
    examples: ['google', 'openai', 'ahrefs'],
    frequency: 'high',
    caseSensitive: false,
    nullable: true
  },

  'ua.crawler_verifiable': {
    label: '爬虫可验证性',
    category: '爬虫识别',
    type: 'bool',
    hint: '是否支持通过 DNS 反查验证爬虫真实性',
    options: [
      { value: true, label: '可验证', desc: '支持官方 DNS 验证' },
      { value: false, label: '不可验证', desc: '无官方验证途径' }
    ],
    examples: [true, false],
    frequency: 'low'
  },

  'ua.device_type': {
    label: '设备类型',
    category: '设备信息',
    type: 'enum',
    hint: '访问者使用的设备类型',
    placeholder: '选择设备类型',
    options: [
      { value: 'desktop', label: '桌面设备', desc: '台式机/笔记本电脑' },
      { value: 'mobile', label: '手机', desc: '智能手机' },
      { value: 'tablet', label: '平板电脑', desc: 'iPad/Android 平板' },
      { value: 'bot', label: '爬虫', desc: '自动化程序' },
      { value: 'unknown', label: '未知', desc: '无法识别' }
    ],
    examples: ['desktop', 'mobile', 'bot'],
    frequency: 'high',
    nullable: true
  },

  'ua.os': {
    label: '操作系统',
    category: '设备信息',
    type: 'enum',
    hint: '访问者的操作系统',
    placeholder: '选择操作系统',
    options: [
      { value: 'windows', label: 'Windows', desc: 'Windows 7/8/10/11' },
      { value: 'macos', label: 'macOS', desc: 'Apple macOS' },
      { value: 'linux', label: 'Linux', desc: 'Linux 发行版' },
      { value: 'android', label: 'Android', desc: 'Android 系统' },
      { value: 'ios', label: 'iOS', desc: 'Apple iOS' },
      { value: 'unknown', label: '未知', desc: '无法识别' }
    ],
    examples: ['windows', 'android', 'ios'],
    frequency: 'high',
    caseSensitive: false,
    nullable: true
  },

  'ua.browser': {
    label: '浏览器',
    category: '设备信息',
    type: 'enum',
    hint: '访问者使用的浏览器',
    placeholder: '选择浏览器',
    options: [
      { value: 'chrome', label: 'Chrome', desc: 'Google Chrome' },
      { value: 'safari', label: 'Safari', desc: 'Apple Safari' },
      { value: 'firefox', label: 'Firefox', desc: 'Mozilla Firefox' },
      { value: 'edge', label: 'Edge', desc: 'Microsoft Edge' },
      { value: 'opera', label: 'Opera', desc: 'Opera Browser' },
      { value: 'ie', label: 'IE', desc: 'Internet Explorer' },
      { value: 'unknown', label: '未知', desc: '无法识别' }
    ],
    examples: ['chrome', 'safari', 'firefox'],
    frequency: 'high',
    caseSensitive: false,
    nullable: true
  },

  'ua.client_type': {
    label: '客户端类型',
    category: '设备信息',
    type: 'enum',
    hint: '客户端程序的类型',
    placeholder: '选择客户端类型',
    options: [
      { value: 'browser', label: '浏览器', desc: '正常浏览器' },
      { value: 'bot', label: '爬虫', desc: '爬虫程序' },
      { value: 'library', label: '程序库', desc: 'HTTP 库' },
      { value: 'mobile_app', label: '移动应用', desc: '移动端 App' },
      { value: 'unknown', label: '未知', desc: '无法识别' }
    ],
    examples: ['browser', 'bot', 'library'],
    frequency: 'medium',
    nullable: true
  }
}

// ========== 请求属性字段 ==========
const REQUEST_FIELDS: Record<string, FieldMetadata> = {
  'request.method': {
    label: 'HTTP 方法',
    category: '请求属性',
    type: 'enum',
    hint: 'HTTP 请求方法',
    placeholder: '选择 HTTP 方法',
    options: [
      { value: 'GET', label: 'GET', desc: '获取资源' },
      { value: 'POST', label: 'POST', desc: '提交数据' },
      { value: 'PUT', label: 'PUT', desc: '更新资源' },
      { value: 'DELETE', label: 'DELETE', desc: '删除资源' },
      { value: 'PATCH', label: 'PATCH', desc: '部分更新' },
      { value: 'HEAD', label: 'HEAD', desc: '获取响应头' },
      { value: 'OPTIONS', label: 'OPTIONS', desc: '查询支持的方法' }
    ],
    examples: ['GET', 'POST', 'DELETE'],
    frequency: 'high',
    caseSensitive: true
  },

  'request.path': {
    label: '请求路径',
    category: '请求属性',
    type: 'string',
    hint: '访问的 URL 路径（不含域名和查询参数）',
    placeholder: '如：/api/login 或 /admin',
    examples: ['/api/login', '/admin', '/wp-admin', '/api/users'],
    frequency: 'high',
    caseSensitive: true
  },

  'request.host': {
    label: '请求域名',
    category: '请求属性',
    type: 'string',
    hint: '请求的目标域名（Host 头）',
    placeholder: '如：example.com',
    examples: ['example.com', 'api.example.com', 'www.example.com'],
    frequency: 'medium',
    caseSensitive: false
  },

  'request.scheme': {
    label: '协议类型',
    category: '请求属性',
    type: 'enum',
    hint: 'HTTP 或 HTTPS 协议',
    options: [
      { value: 'http', label: 'HTTP', desc: '非加密协议' },
      { value: 'https', label: 'HTTPS', desc: '加密协议' }
    ],
    examples: ['https', 'http'],
    frequency: 'low'
  },

  'request.referer': {
    label: 'Referer 来源',
    category: '请求属性',
    type: 'string',
    hint: 'HTTP Referer 头，表示请求来源页面',
    placeholder: '如：https://google.com',
    examples: ['https://google.com', 'https://baidu.com'],
    frequency: 'medium',
    caseSensitive: false,
    nullable: true
  },

  'request.query': {
    label: '查询参数',
    category: '请求属性',
    type: 'string',
    hint: 'URL 查询字符串',
    placeholder: '如：id=123&type=admin',
    examples: ['id=123', 'token=abc', 'page=1'],
    frequency: 'low',
    caseSensitive: true,
    nullable: true
  }
}

// ========== 情报数据字段 ==========
const INTEL_FIELDS: Record<string, FieldMetadata> = {
  'intel.risk_level': {
    label: '情报风险等级',
    category: '情报数据',
    type: 'enum',
    hint: '后台情报库标记的风险等级',
    options: [
      { value: 'low', label: '低风险', desc: '正常访问' },
      { value: 'medium', label: '中风险', desc: '可疑行为' },
      { value: 'high', label: '高风险', desc: '恶意行为' },
      { value: 'critical', label: '严重风险', desc: '已知攻击' }
    ],
    examples: ['low', 'medium', 'high'],
    frequency: 'medium',
    nullable: true
  },

  'intel.crawler_category': {
    label: '情报爬虫类别',
    category: '情报数据',
    type: 'enum',
    hint: '后台情报库标记的爬虫类别',
    placeholder: '选择爬虫类别',
    options: [
      { value: 'search_engine', label: '搜索引擎', desc: 'Google/Bing/百度等' },
      { value: 'social', label: '社交媒体', desc: '微信/Twitter等' },
      { value: 'ai_crawler', label: 'AI 爬虫', desc: 'GPTBot/ClaudeBot等' },
      { value: 'seo', label: 'SEO 工具', desc: 'Ahrefs/Semrush等' },
      { value: 'monitoring', label: '监控探测', desc: 'UptimeRobot等' },
      { value: 'security', label: '安全扫描器', desc: 'sqlmap/nikto等' }
    ],
    examples: ['search_engine', 'ai_crawler'],
    frequency: 'medium',
    nullable: true
  },

  'intel.is_legitimate_crawler': {
    label: '合法爬虫标识',
    category: '情报数据',
    type: 'bool',
    hint: '情报库是否认定为合法爬虫',
    options: [
      { value: true, label: '是', desc: '已认证的合法爬虫' },
      { value: false, label: '否', desc: '非合法爬虫' }
    ],
    examples: [true, false],
    frequency: 'low',
    nullable: true
  },

  'intel.tags': {
    label: '情报标签',
    category: '情报数据',
    type: 'string',
    hint: '后台添加的自定义标签',
    placeholder: '如：vip-client, test-user',
    examples: ['vip-client', 'blacklist', 'whitelist'],
    frequency: 'low',
    caseSensitive: false,
    nullable: true
  }
}

// ========== 风险评分字段 ==========
const SCORE_FIELDS: Record<string, FieldMetadata> = {
  'score.total': {
    label: '综合风险分',
    category: '风险评估',
    type: 'number',
    hint: '系统计算的综合风险评分（0-100）',
    placeholder: '0-100',
    range: { min: 0, max: 100 },
    examples: [30, 60, 85],
    frequency: 'high',
    recommendations: [
      { range: '0-30', label: '低风险', color: 'success', desc: '正常用户，建议放行' },
      { range: '31-60', label: '中风险', color: 'warning', desc: '可疑行为，建议限流或挑战' },
      { range: '61-100', label: '高风险', color: 'danger', desc: '恶意行为，建议阻断' }
    ]
  },

  'score.ip': {
    label: 'IP 风险分',
    category: '风险评估',
    type: 'number',
    hint: 'IP 维度的风险评分（0-100）',
    placeholder: '0-100',
    range: { min: 0, max: 100 },
    examples: [20, 50, 80],
    frequency: 'medium'
  },

  'score.ua': {
    label: 'UA 风险分',
    category: '风险评估',
    type: 'number',
    hint: 'User-Agent 维度的风险评分（0-100）',
    placeholder: '0-100',
    range: { min: 0, max: 100 },
    examples: [15, 45, 75],
    frequency: 'medium'
  },

  'score.behavior': {
    label: '行为风险分',
    category: '风险评估',
    type: 'number',
    hint: '行为模式的风险评分（0-100）',
    placeholder: '0-100',
    range: { min: 0, max: 100 },
    examples: [25, 55, 90],
    frequency: 'medium'
  }
}

// ========== 设备画像字段 ==========
const DEVICE_FIELDS: Record<string, FieldMetadata> = {
  'device.fingerprint': {
    label: '设备指纹',
    category: '设备画像',
    type: 'string',
    hint: '设备唯一标识符',
    placeholder: '32位哈希值',
    examples: ['a1b2c3d4e5f6...', 'f9e8d7c6b5a4...'],
    frequency: 'low',
    nullable: true
  },

  'device.screen_resolution': {
    label: '屏幕分辨率',
    category: '设备画像',
    type: 'string',
    hint: '设备屏幕分辨率',
    placeholder: '如：1920x1080',
    examples: ['1920x1080', '1366x768', '2560x1440'],
    frequency: 'low',
    nullable: true
  },

  'device.language': {
    label: '系统语言',
    category: '设备画像',
    type: 'enum',
    hint: '设备或浏览器的首选语言',
    options: [
      { value: 'zh-CN', label: '简体中文', desc: '中国大陆' },
      { value: 'zh-TW', label: '繁体中文', desc: '中国台湾/香港' },
      { value: 'en-US', label: '英语（美国）', desc: '美式英语' },
      { value: 'en-GB', label: '英语（英国）', desc: '英式英语' },
      { value: 'ja-JP', label: '日语', desc: '日本' },
      { value: 'ko-KR', label: '韩语', desc: '韩国' }
    ],
    examples: ['zh-CN', 'en-US', 'ja-JP'],
    frequency: 'low',
    nullable: true
  },

  'device.timezone': {
    label: '时区',
    category: '设备画像',
    type: 'string',
    hint: '设备所在时区',
    placeholder: '如：Asia/Shanghai, America/New_York',
    examples: ['Asia/Shanghai', 'America/New_York', 'Europe/London'],
    frequency: 'low',
    nullable: true
  }
}

// ========== 会话属性字段 ==========
const SESSION_FIELDS: Record<string, FieldMetadata> = {
  'session.page_views': {
    label: '会话页面浏览数',
    category: '会话属性',
    type: 'number',
    hint: '当前会话中的页面浏览次数',
    placeholder: '如：5',
    range: { min: 0, max: 10000 },
    examples: [1, 5, 10],
    frequency: 'low',
    nullable: true
  },

  'session.duration': {
    label: '会话时长',
    category: '会话属性',
    type: 'number',
    hint: '会话持续时间（秒）',
    placeholder: '单位：秒',
    range: { min: 0, max: 86400 },
    unit: '秒',
    examples: [30, 300, 1800],
    frequency: 'low',
    nullable: true
  },

  'session.is_new': {
    label: '是否新会话',
    category: '会话属性',
    type: 'bool',
    hint: '是否为首次访问（新会话）',
    options: [
      { value: true, label: '是', desc: '首次访问' },
      { value: false, label: '否', desc: '回访用户' }
    ],
    examples: [true, false],
    frequency: 'low',
    nullable: true
  }
}

// ========== 裁决结果字段 ==========
const VERDICT_FIELDS: Record<string, FieldMetadata> = {
  'verdict.decision': {
    label: '裁决结果',
    category: '裁决结果',
    type: 'enum',
    hint: '风控引擎的最终裁决',
    options: [
      { value: 'benign', label: '正常', desc: '正常流量' },
      { value: 'suspicious', label: '可疑', desc: '可疑流量' },
      { value: 'hostile', label: '恶意', desc: '恶意流量' }
    ],
    examples: ['benign', 'suspicious', 'hostile'],
    frequency: 'high'
  },

  'verdict.mechanism': {
    label: '处置机制',
    category: '裁决结果',
    type: 'enum',
    hint: '实际执行的处置动作',
    options: [
      { value: 'pass', label: '放行', desc: '直接放行' },
      { value: 'challenge', label: '挑战', desc: 'JS挑战/验证码' },
      { value: 'deny', label: '拒绝', desc: '阻断请求' },
      { value: 'not_found', label: '404', desc: '返回404' },
      { value: 'rate_limit', label: '限流', desc: '速率限制' }
    ],
    examples: ['pass', 'challenge', 'deny'],
    frequency: 'high'
  },

  'verdict.rule_id': {
    label: '触发规则ID',
    category: '裁决结果',
    type: 'number',
    hint: '触发的规则编号',
    placeholder: '如：1001',
    examples: [1001, 1002, 1003],
    frequency: 'medium',
    nullable: true
  },

  'verdict.rule_name': {
    label: '触发规则名称',
    category: '裁决结果',
    type: 'string',
    hint: '触发的规则名称',
    placeholder: '如：阻断 AI 爬虫',
    examples: ['阻断 AI 爬虫', '放行搜索引擎', 'VPN 拦截'],
    frequency: 'medium',
    caseSensitive: false,
    nullable: true
  }
}

// ========== 合并所有字段 ==========
export const ALL_FIELDS: Record<string, FieldMetadata> = {
  ...IP_FIELDS,
  ...UA_FIELDS,
  ...REQUEST_FIELDS,
  ...INTEL_FIELDS,
  ...SCORE_FIELDS,
  ...DEVICE_FIELDS,
  ...SESSION_FIELDS,
  ...VERDICT_FIELDS
}

// ========== 字段分组 ==========
export const FIELD_GROUPS = [
  {
    name: 'popular',
    label: '常用字段',
    icon: 'Star',
    fields: [
      'ua.crawler_category',
      'ua.crawler_vendor',
      'ua.crawler_name',
      'ua.is_bot',
      'ip.country',
      'ip.isVpn',
      'ip.isProxy',
      'request.path',
      'request.method',
      'score.total',
      'verdict.decision'
    ]
  },
  {
    name: 'crawler',
    label: '爬虫识别',
    icon: 'Cpu',
    fields: [
      'ua.is_bot',
      'ua.crawler_category',
      'ua.crawler_vendor',
      'ua.crawler_name',
      'ua.crawler_verifiable',
      'intel.crawler_category',
      'intel.is_legitimate_crawler'
    ]
  },
  {
    name: 'geo',
    label: '地理位置',
    icon: 'Location',
    fields: [
      'ip.country',
      'ip.continent',
      'ip.city',
      'device.timezone',
      'device.language'
    ]
  },
  {
    name: 'security',
    label: '网络安全',
    icon: 'Lock',
    fields: [
      'ip.isVpn',
      'ip.isProxy',
      'ip.isTor',
      'ip.isDatacenter',
      'ip.isHosting'
    ]
  },
  {
    name: 'device',
    label: '设备信息',
    icon: 'Monitor',
    fields: [
      'ua.device_type',
      'ua.os',
      'ua.browser',
      'ua.client_type',
      'device.fingerprint',
      'device.screen_resolution'
    ]
  },
  {
    name: 'ip',
    label: 'IP画像',
    icon: 'Connection',
    fields: [
      'ip.country',
      'ip.continent',
      'ip.city',
      'ip.asn',
      'ip.asnOrg'
    ]
  },
  {
    name: 'request',
    label: '请求属性',
    icon: 'Document',
    fields: [
      'request.method',
      'request.path',
      'request.host',
      'request.scheme',
      'request.referer',
      'request.query'
    ]
  },
  {
    name: 'score',
    label: '风险评估',
    icon: 'Warning',
    fields: [
      'score.total',
      'score.ip',
      'score.ua',
      'score.behavior'
    ]
  },
  {
    name: 'intel',
    label: '情报数据',
    icon: 'DataAnalysis',
    fields: [
      'intel.risk_level',
      'intel.crawler_category',
      'intel.is_legitimate_crawler',
      'intel.tags'
    ]
  },
  {
    name: 'session',
    label: '会话属性',
    icon: 'Timer',
    fields: [
      'session.page_views',
      'session.duration',
      'session.is_new'
    ]
  },
  {
    name: 'verdict',
    label: '裁决结果',
    icon: 'CircleCheck',
    fields: [
      'verdict.decision',
      'verdict.mechanism',
      'verdict.rule_id',
      'verdict.rule_name'
    ]
  }
]

// ========== 工具函数 ==========

/**
 * 获取字段元数据
 */
export function getFieldMetadata(fieldKey: string): FieldMetadata | undefined {
  return ALL_FIELDS[fieldKey]
}

/**
 * 获取字段标签
 */
export function getFieldLabel(fieldKey: string): string {
  return ALL_FIELDS[fieldKey]?.label || fieldKey
}

/**
 * 获取字段类型
 */
export function getFieldType(fieldKey: string): string {
  return ALL_FIELDS[fieldKey]?.type || 'string'
}

/**
 * 检查字段是否有预定义选项
 */
export function hasFieldOptions(fieldKey: string): boolean {
  const metadata = ALL_FIELDS[fieldKey]
  return metadata?.type === 'enum' || metadata?.type === 'bool'
}

/**
 * 获取字段选项
 */
export function getFieldOptions(fieldKey: string): FieldOption[] {
  return ALL_FIELDS[fieldKey]?.options || []
}

/**
 * 获取字段示例
 */
export function getFieldExamples(fieldKey: string): any[] {
  return ALL_FIELDS[fieldKey]?.examples || []
}

/**
 * 获取字段提示
 */
export function getFieldHint(fieldKey: string): string {
  return ALL_FIELDS[fieldKey]?.hint || ''
}

/**
 * 获取字段占位符
 */
export function getFieldPlaceholder(fieldKey: string): string {
  return ALL_FIELDS[fieldKey]?.placeholder || ''
}

/**
 * 搜索字段
 */
export function searchFields(keyword: string): Array<{ key: string; metadata: FieldMetadata }> {
  if (!keyword) return []
  
  const lowerKeyword = keyword.toLowerCase()
  const results: Array<{ key: string; metadata: FieldMetadata }> = []
  
  for (const [key, metadata] of Object.entries(ALL_FIELDS)) {
    // 搜索字段key
    if (key.toLowerCase().includes(lowerKeyword)) {
      results.push({ key, metadata })
      continue
    }
    
    // 搜索字段标签
    if (metadata.label.toLowerCase().includes(lowerKeyword)) {
      results.push({ key, metadata })
      continue
    }
    
    // 搜索字段提示
    if (metadata.hint.toLowerCase().includes(lowerKeyword)) {
      results.push({ key, metadata })
      continue
    }
    
    // 搜索字段分类
    if (metadata.category.toLowerCase().includes(lowerKeyword)) {
      results.push({ key, metadata })
      continue
    }
  }
  
  return results
}

/**
 * 获取常用字段
 */
export function getPopularFields(): Array<{ key: string; metadata: FieldMetadata }> {
  return Object.entries(ALL_FIELDS)
    .filter(([, metadata]) => metadata.frequency === 'high')
    .map(([key, metadata]) => ({ key, metadata }))
    .sort((a, b) => a.metadata.label.localeCompare(b.metadata.label))
}

/**
 * 按分类获取字段
 */
export function getFieldsByCategory(category: string): Array<{ key: string; metadata: FieldMetadata }> {
  return Object.entries(ALL_FIELDS)
    .filter(([, metadata]) => metadata.category === category)
    .map(([key, metadata]) => ({ key, metadata }))
}

/**
 * 获取字段建议
 */
export function getFieldRecommendations(fieldKey: string): FieldMetadata['recommendations'] {
  return ALL_FIELDS[fieldKey]?.recommendations
}

/**
 * 格式化字段值用于显示
 */
export function formatFieldValue(fieldKey: string, value: any): string {
  const metadata = ALL_FIELDS[fieldKey]
  if (!metadata) return String(value)
  
  // 布尔类型
  if (metadata.type === 'bool') {
    return value ? '是' : '否'
  }
  
  // 枚举类型 - 查找对应的标签
  if (metadata.type === 'enum' && metadata.options) {
    const option = metadata.options.find(opt => opt.value === value)
    return option?.label || String(value)
  }
  
  // 数字类型 - 添加单位
  if (metadata.type === 'number' && metadata.unit) {
    return `${value} ${metadata.unit}`
  }
  
  return String(value)
}

/**
 * 获取字段值的颜色标签类型
 */
export function getFieldValueTagType(fieldKey: string, value: any): 'success' | 'warning' | 'danger' | 'info' | '' {
  const metadata = ALL_FIELDS[fieldKey]
  
  // 爬虫类别
  if (fieldKey === 'ua.crawler_category') {
    const colorMap: Record<string, any> = {
      'search_engine': 'success',
      'social': 'info',
      'ai_crawler': 'warning',
      'seo': 'warning',
      'monitoring': 'info',
      'security': 'danger',
      'library': 'warning',
      'feed': 'info',
      'archive': 'info'
    }
    return colorMap[value] || ''
  }
  
  // 风险等级
  if (fieldKey === 'intel.risk_level') {
    const colorMap: Record<string, any> = {
      'low': 'success',
      'medium': 'warning',
      'high': 'danger',
      'critical': 'danger'
    }
    return colorMap[value] || ''
  }
  
  // 裁决结果
  if (fieldKey === 'verdict.decision') {
    const colorMap: Record<string, any> = {
      'benign': 'success',
      'suspicious': 'warning',
      'hostile': 'danger'
    }
    return colorMap[value] || ''
  }
  
  // 处置机制
  if (fieldKey === 'verdict.mechanism') {
    const colorMap: Record<string, any> = {
      'pass': 'success',
      'challenge': 'warning',
      'deny': 'danger',
      'not_found': 'info',
      'rate_limit': 'warning'
    }
    return colorMap[value] || ''
  }
  
  // 布尔类型 - 根据风险级别
  if (metadata?.type === 'bool') {
    if (metadata.riskLevel === 'high') {
      return value ? 'danger' : 'success'
    }
    if (metadata.riskLevel === 'medium') {
      return value ? 'warning' : 'info'
    }
    return value ? 'success' : 'info'
  }
  
  return ''
}

/**
 * 验证字段值
 */
export function validateFieldValue(fieldKey: string, value: any): { valid: boolean; message?: string } {
  const metadata = ALL_FIELDS[fieldKey]
  if (!metadata) {
    return { valid: true }
  }
  
  // 必填校验
  if (!metadata.nullable && (value === null || value === undefined || value === '')) {
    return { valid: false, message: '此字段不能为空' }
  }
  
  // 数字类型范围校验
  if (metadata.type === 'number' && metadata.range) {
    const numValue = Number(value)
    if (isNaN(numValue)) {
      return { valid: false, message: '请输入有效的数字' }
    }
    if (numValue < metadata.range.min || numValue > metadata.range.max) {
      return { valid: false, message: `值必须在 ${metadata.range.min} 到 ${metadata.range.max} 之间` }
    }
  }
  
  // 枚举类型校验
  if (metadata.type === 'enum' && metadata.options && value) {
    const validValues = metadata.options.map(opt => opt.value)
    if (!validValues.includes(value)) {
      return { valid: false, message: '请选择有效的选项' }
    }
  }
  
  return { valid: true }
}

/**
 * 获取字段的匹配示例
 */
export function getFieldMatchExamples(fieldKey: string, operator: string, value: any): string[] {
  const metadata = ALL_FIELDS[fieldKey]
  if (!metadata) return []
  
  // 简单情况：直接返回示例
  if (operator === 'eq' && metadata.examples) {
    if (metadata.examples.includes(value)) {
      return [String(value)]
    }
  }
  
  // 包含操作
  if (operator === 'contains' && typeof value === 'string') {
    return metadata.examples
      ?.filter(ex => String(ex).toLowerCase().includes(value.toLowerCase()))
      .map(String) || []
  }
  
  // 默认返回前3个示例
  return metadata.examples?.slice(0, 3).map(String) || []
}

/**
 * 获取所有分类
 */
export function getAllCategories(): string[] {
  const categories = new Set<string>()
  Object.values(ALL_FIELDS).forEach(metadata => {
    categories.add(metadata.category)
  })
  return Array.from(categories).sort()
}

/**
 * 统计字段数量
 */
export function getFieldStats() {
  const total = Object.keys(ALL_FIELDS).length
  const byCategory: Record<string, number> = {}
  const byType: Record<string, number> = {}
  const byFrequency: Record<string, number> = {}
  
  Object.values(ALL_FIELDS).forEach(metadata => {
    // 按分类统计
    byCategory[metadata.category] = (byCategory[metadata.category] || 0) + 1
    
    // 按类型统计
    byType[metadata.type] = (byType[metadata.type] || 0) + 1
    
    // 按频率统计
    if (metadata.frequency) {
      byFrequency[metadata.frequency] = (byFrequency[metadata.frequency] || 0) + 1
    }
  })
  
  return {
    total,
    byCategory,
    byType,
    byFrequency
  }
}


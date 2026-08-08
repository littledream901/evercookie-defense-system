/**
 * 爬虫详细信息映射表
 * 根据 crawler_name 解析出完整的爬虫信息
 */

export interface CrawlerDetail {
  /** 爬虫显示名称 */
  displayName: string
  /** 所属厂商 */
  vendor: string
  /** 厂商显示名称 */
  vendorName: string
  /** 粗分类 */
  category: string
  /** 细分类（用途） */
  subcategory: string
  /** 所属产品 */
  product: string
  /** 用途描述 */
  purpose: string
  /** 图标 */
  icon: string
  /** 文档链接 */
  docUrl?: string
}

/** 爬虫详细信息数据库 */
export const CRAWLER_DETAILS: Record<string, CrawlerDetail> = {
  // ========== Google 爬虫 ==========
  'googlebot': {
    displayName: 'Googlebot',
    vendor: 'google',
    vendorName: 'Google',
    category: 'search_engine',
    subcategory: 'web_search',
    product: 'Google Search',
    purpose: '抓取和索引网页内容',
    icon: '🔍',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/googlebot'
  },
  'googlebot-image': {
    displayName: 'Googlebot-Image',
    vendor: 'google',
    vendorName: 'Google',
    category: 'search_engine',
    subcategory: 'image_search',
    product: 'Google Images',
    purpose: '抓取和索引图片',
    icon: '🖼️',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/googlebot'
  },
  'googlebot-video': {
    displayName: 'Googlebot-Video',
    vendor: 'google',
    vendorName: 'Google',
    category: 'search_engine',
    subcategory: 'video_search',
    product: 'Google Video',
    purpose: '抓取和索引视频',
    icon: '🎬',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/googlebot'
  },
  'googlebot-news': {
    displayName: 'Googlebot-News',
    vendor: 'google',
    vendorName: 'Google',
    category: 'search_engine',
    subcategory: 'news_search',
    product: 'Google News',
    purpose: '抓取新闻文章',
    icon: '📰',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/googlebot'
  },
  'google-extended': {
    displayName: 'Google-Extended',
    vendor: 'google',
    vendorName: 'Google',
    category: 'ai_crawler',
    subcategory: 'ai_training',
    product: 'Google AI',
    purpose: '为生成式AI模型收集训练数据',
    icon: '🤖',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers'
  },
  'adsbot-google': {
    displayName: 'AdsBot-Google',
    vendor: 'google',
    vendorName: 'Google',
    category: 'advertising',
    subcategory: 'ad_quality',
    product: 'Google Ads',
    purpose: '检查广告着陆页质量',
    icon: '💰',
    docUrl: 'https://support.google.com/google-ads/answer/12496941'
  },
  'adsbot-google-mobile': {
    displayName: 'AdsBot-Google-Mobile',
    vendor: 'google',
    vendorName: 'Google',
    category: 'advertising',
    subcategory: 'ad_quality_mobile',
    product: 'Google Ads',
    purpose: '检查移动广告着陆页质量',
    icon: '📱',
    docUrl: 'https://support.google.com/google-ads/answer/12496941'
  },
  'mediapartners-google': {
    displayName: 'Mediapartners-Google',
    vendor: 'google',
    vendorName: 'Google',
    category: 'advertising',
    subcategory: 'contextual_ads',
    product: 'Google AdSense',
    purpose: '分析页面内容以投放相关广告',
    icon: '📊',
    docUrl: 'https://support.google.com/adsense/answer/99376'
  },
  'googlebot-mobile': {
    displayName: 'Googlebot-Mobile',
    vendor: 'google',
    vendorName: 'Google',
    category: 'search_engine',
    subcategory: 'mobile_search',
    product: 'Google Mobile Search',
    purpose: '抓取移动版网页',
    icon: '📱',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/googlebot'
  },
  'google-inspectiontool': {
    displayName: 'Google-InspectionTool',
    vendor: 'google',
    vendorName: 'Google',
    category: 'monitoring',
    subcategory: 'seo_tool',
    product: 'Google Search Console',
    purpose: 'Search Console URL检查工具',
    icon: '🔧',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers'
  },
  'google-read-aloud': {
    displayName: 'Google-Read-Aloud',
    vendor: 'google',
    vendorName: 'Google',
    category: 'accessibility',
    subcategory: 'text_to_speech',
    product: 'Google Assistant',
    purpose: '为语音朗读功能抓取内容',
    icon: '🔊',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers'
  },
  'feedfetcher-google': {
    displayName: 'FeedFetcher-Google',
    vendor: 'google',
    vendorName: 'Google',
    category: 'feed_reader',
    subcategory: 'rss_atom',
    product: 'Google Feed Services',
    purpose: '抓取RSS/Atom订阅源',
    icon: '📡'
  },
  'google-site-verification': {
    displayName: 'Google-Site-Verification',
    vendor: 'google',
    vendorName: 'Google',
    category: 'monitoring',
    subcategory: 'site_ownership',
    product: 'Google Services',
    purpose: '验证网站所有权',
    icon: '✅'
  },
  'storebot-google': {
    displayName: 'Storebot-Google',
    vendor: 'google',
    vendorName: 'Google',
    category: 'e_commerce',
    subcategory: 'product_indexing',
    product: 'Google Shopping',
    purpose: '抓取和索引商品信息',
    icon: '🛒',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers'
  },
  'googleweblight': {
    displayName: 'Google Web Light',
    vendor: 'google',
    vendorName: 'Google',
    category: 'accessibility',
    subcategory: 'page_optimization',
    product: 'Google Web Light',
    purpose: '为慢速网络优化网页加载',
    icon: '⚡',
    docUrl: 'https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers'
  },

  // ========== Bing 爬虫 ==========
  'bingbot': {
    displayName: 'Bingbot',
    vendor: 'bing',
    vendorName: 'Microsoft Bing',
    category: 'search_engine',
    subcategory: 'web_search',
    product: 'Bing Search',
    purpose: '抓取和索引网页内容',
    icon: '🔍',
    docUrl: 'https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0'
  },
  'bingpreview': {
    displayName: 'BingPreview',
    vendor: 'bing',
    vendorName: 'Microsoft Bing',
    category: 'search_engine',
    subcategory: 'page_preview',
    product: 'Bing Search',
    purpose: '生成搜索结果预览',
    icon: '👁️',
    docUrl: 'https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0'
  },
  'adidxbot': {
    displayName: 'AdIdxBot',
    vendor: 'bing',
    vendorName: 'Microsoft Bing',
    category: 'advertising',
    subcategory: 'ad_indexing',
    product: 'Microsoft Advertising',
    purpose: '索引广告内容',
    icon: '💼',
    docUrl: 'https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0'
  },
  'msnbot': {
    displayName: 'MSNBot',
    vendor: 'bing',
    vendorName: 'Microsoft',
    category: 'search_engine',
    subcategory: 'web_search',
    product: 'MSN',
    purpose: 'MSN搜索引擎爬虫（已废弃）',
    icon: '🔍'
  },

  // ========== OpenAI 爬虫 ==========
  'gptbot': {
    displayName: 'GPTBot',
    vendor: 'openai',
    vendorName: 'OpenAI',
    category: 'ai_crawler',
    subcategory: 'ai_training',
    product: 'ChatGPT / GPT Models',
    purpose: '为AI模型收集训练数据',
    icon: '🤖',
    docUrl: 'https://platform.openai.com/docs/gptbot'
  },
  'chatgpt-user': {
    displayName: 'ChatGPT-User',
    vendor: 'openai',
    vendorName: 'OpenAI',
    category: 'ai_crawler',
    subcategory: 'browsing',
    product: 'ChatGPT Browsing',
    purpose: 'ChatGPT联网浏览功能',
    icon: '💬',
    docUrl: 'https://platform.openai.com/docs/plugins/bot'
  },
  'oai-searchbot': {
    displayName: 'OAI-SearchBot',
    vendor: 'openai',
    vendorName: 'OpenAI',
    category: 'ai_crawler',
    subcategory: 'search_indexing',
    product: 'SearchGPT',
    purpose: 'SearchGPT搜索索引',
    icon: '🔎',
    docUrl: 'https://help.openai.com/en/articles/8555545-searchgpt-crawling'
  },

  // ========== Anthropic 爬虫 ==========
  'claudebot': {
    displayName: 'ClaudeBot',
    vendor: 'anthropic',
    vendorName: 'Anthropic',
    category: 'ai_crawler',
    subcategory: 'ai_training',
    product: 'Claude AI',
    purpose: '为Claude模型收集训练数据',
    icon: '🧠',
    docUrl: 'https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web'
  },

  // ========== Baidu 爬虫 ==========
  'baiduspider': {
    displayName: 'Baiduspider',
    vendor: 'baidu',
    vendorName: '百度',
    category: 'search_engine',
    subcategory: 'web_search',
    product: '百度搜索',
    purpose: '抓取和索引网页',
    icon: '🔍',
    docUrl: 'https://www.baidu.com/search/robots.html'
  },
  'baiduspider-image': {
    displayName: 'Baiduspider-Image',
    vendor: 'baidu',
    vendorName: '百度',
    category: 'search_engine',
    subcategory: 'image_search',
    product: '百度图片',
    purpose: '抓取图片',
    icon: '🖼️'
  },
  'baiduspider-video': {
    displayName: 'Baiduspider-Video',
    vendor: 'baidu',
    vendorName: '百度',
    category: 'search_engine',
    subcategory: 'video_search',
    product: '百度视频',
    purpose: '抓取视频',
    icon: '🎬'
  },
  'baiduspider-news': {
    displayName: 'Baiduspider-News',
    vendor: 'baidu',
    vendorName: '百度',
    category: 'search_engine',
    subcategory: 'news_search',
    product: '百度新闻',
    purpose: '抓取新闻',
    icon: '📰'
  },

  // ========== Facebook 爬虫 ==========
  'facebookexternalhit': {
    displayName: 'FacebookExternalHit',
    vendor: 'facebook',
    vendorName: 'Meta (Facebook)',
    category: 'social_media',
    subcategory: 'link_preview',
    product: 'Facebook',
    purpose: '生成链接分享预览',
    icon: '👍',
    docUrl: 'https://developers.facebook.com/docs/sharing/webmasters/crawler'
  },
  'facebot': {
    displayName: 'Facebot',
    vendor: 'facebook',
    vendorName: 'Meta (Facebook)',
    category: 'social_media',
    subcategory: 'link_preview',
    product: 'Facebook',
    purpose: '抓取Open Graph元数据',
    icon: '🤖'
  },

  // ========== 其他主流爬虫 ==========
  'bytespider': {
    displayName: 'Bytespider',
    vendor: 'bytedance',
    vendorName: '字节跳动',
    category: 'search_engine',
    subcategory: 'web_search',
    product: '抖音搜索 / 今日头条',
    purpose: '搜索引擎索引',
    icon: '🔍'
  },
  'bytedance': {
    displayName: 'Bytedance',
    vendor: 'bytedance',
    vendorName: '字节跳动',
    category: 'ai_crawler',
    subcategory: 'ai_training',
    product: '字节AI',
    purpose: 'AI训练数据收集',
    icon: '🤖'
  },
  'applebot': {
    displayName: 'Applebot',
    vendor: 'apple',
    vendorName: 'Apple',
    category: 'search_engine',
    subcategory: 'web_search',
    product: 'Spotlight / Siri',
    purpose: 'Spotlight搜索和Siri知识库',
    icon: '🍎',
    docUrl: 'https://support.apple.com/en-us/119829'
  },
  'yandexbot': {
    displayName: 'YandexBot',
    vendor: 'yandex',
    vendorName: 'Yandex',
    category: 'search_engine',
    subcategory: 'web_search',
    product: 'Yandex Search',
    purpose: '抓取和索引网页',
    icon: '🔍',
    docUrl: 'https://yandex.com/support/webmaster/robot-workings/check-yandex-robots.html'
  },
  'duckduckbot': {
    displayName: 'DuckDuckBot',
    vendor: 'duckduckgo',
    vendorName: 'DuckDuckGo',
    category: 'search_engine',
    subcategory: 'web_search',
    product: 'DuckDuckGo Search',
    purpose: '隐私搜索引擎爬虫',
    icon: '🦆',
    docUrl: 'https://help.duckduckgo.com/duckduckgo-help-pages/results/duckduckbot/'
  },
  'slackbot': {
    displayName: 'Slackbot',
    vendor: 'slack',
    vendorName: 'Slack',
    category: 'social_media',
    subcategory: 'link_preview',
    product: 'Slack',
    purpose: '生成链接预览卡片',
    icon: '💬',
    docUrl: 'https://api.slack.com/robots'
  },
  'twitterbot': {
    displayName: 'Twitterbot',
    vendor: 'twitter',
    vendorName: 'X (Twitter)',
    category: 'social_media',
    subcategory: 'link_preview',
    product: 'X / Twitter',
    purpose: '生成推文链接预览',
    icon: '🐦'
  },
  'linkedinbot': {
    displayName: 'LinkedInBot',
    vendor: 'linkedin',
    vendorName: 'LinkedIn',
    category: 'social_media',
    subcategory: 'link_preview',
    product: 'LinkedIn',
    purpose: '生成职业社交分享预览',
    icon: '💼',
    docUrl: 'https://www.linkedin.com/help/linkedin/answer/a1343820'
  },
  'telegrambot': {
    displayName: 'TelegramBot',
    vendor: 'telegram',
    vendorName: 'Telegram',
    category: 'social_media',
    subcategory: 'link_preview',
    product: 'Telegram',
    purpose: '生成消息链接预览',
    icon: '✈️'
  },
  'amazonbot': {
    displayName: 'Amazonbot',
    vendor: 'amazon',
    vendorName: 'Amazon',
    category: 'e_commerce',
    subcategory: 'product_indexing',
    product: 'Amazon',
    purpose: '商品信息索引',
    icon: '📦',
    docUrl: 'https://developer.amazon.com/amazonbot'
  },
  'semrushbot': {
    displayName: 'SemrushBot',
    vendor: 'semrush',
    vendorName: 'Semrush',
    category: 'seo_tool',
    subcategory: 'seo_analysis',
    product: 'Semrush',
    purpose: 'SEO分析和竞品监控',
    icon: '📊',
    docUrl: 'https://www.semrush.com/bot/'
  },
  'ahrefsbot': {
    displayName: 'AhrefsBot',
    vendor: 'ahrefs',
    vendorName: 'Ahrefs',
    category: 'seo_tool',
    subcategory: 'backlink_analysis',
    product: 'Ahrefs',
    purpose: '外链分析和SEO数据',
    icon: '🔗',
    docUrl: 'https://ahrefs.com/robot'
  },
  'mj12bot': {
    displayName: 'MJ12bot',
    vendor: 'majestic',
    vendorName: 'Majestic',
    category: 'seo_tool',
    subcategory: 'link_intelligence',
    product: 'Majestic SEO',
    purpose: '链接智能分析',
    icon: '👑',
    docUrl: 'https://majestic.com/bot'
  },
  'dotbot': {
    displayName: 'DotBot',
    vendor: 'moz',
    vendorName: 'Moz',
    category: 'seo_tool',
    subcategory: 'seo_metrics',
    product: 'Moz Pro',
    purpose: 'SEO指标收集',
    icon: '📈',
    docUrl: 'https://moz.com/help/moz-procedures/what-is-dotbot'
  },
  'archive.org_bot': {
    displayName: 'Archive.org Bot',
    vendor: 'internetarchive',
    vendorName: 'Internet Archive',
    category: 'archiving',
    subcategory: 'web_archiving',
    product: 'Wayback Machine',
    purpose: '网页存档',
    icon: '📚',
    docUrl: 'https://archive.org/details/archive.org_bot'
  },
  'ia_archiver': {
    displayName: 'IA Archiver',
    vendor: 'internetarchive',
    vendorName: 'Internet Archive',
    category: 'archiving',
    subcategory: 'web_archiving',
    product: 'Internet Archive',
    purpose: '互联网档案馆',
    icon: '🗄️'
  },
  'ccbot': {
    displayName: 'CCBot',
    vendor: 'commoncrawl',
    vendorName: 'Common Crawl',
    category: 'archiving',
    subcategory: 'dataset_building',
    product: 'Common Crawl',
    purpose: '构建开放网页数据集',
    icon: '🌐',
    docUrl: 'https://commoncrawl.org/ccbot'
  },
  'datadoghq': {
    displayName: 'DatadogHQ',
    vendor: 'datadog',
    vendorName: 'Datadog',
    category: 'monitoring',
    subcategory: 'synthetic_monitoring',
    product: 'Datadog Synthetics',
    purpose: '网站监控和性能检测',
    icon: '🐕',
    docUrl: 'https://docs.datadoghq.com/synthetics/'
  },
  'pingdom': {
    displayName: 'Pingdom',
    vendor: 'pingdom',
    vendorName: 'Pingdom',
    category: 'monitoring',
    subcategory: 'uptime_monitoring',
    product: 'Pingdom',
    purpose: '可用性监控',
    icon: '⏱️',
    docUrl: 'https://www.pingdom.com'
  },
  'uptimerobot': {
    displayName: 'UptimeRobot',
    vendor: 'uptimerobot',
    vendorName: 'UptimeRobot',
    category: 'monitoring',
    subcategory: 'uptime_monitoring',
    product: 'UptimeRobot',
    purpose: '网站在线监控',
    icon: '🤖',
    docUrl: 'https://uptimerobot.com'
  },
  'screamingfrogseospider': {
    displayName: 'Screaming Frog SEO Spider',
    vendor: 'screamingfrog',
    vendorName: 'Screaming Frog',
    category: 'seo_tool',
    subcategory: 'site_auditing',
    product: 'SEO Spider',
    purpose: '网站SEO审计',
    icon: '🐸',
    docUrl: 'https://www.screamingfrog.co.uk/seo-spider/'
  }
}

/**
 * 根据 crawler_name 获取详细信息
 */
export function getCrawlerDetail(crawlerName: string | null | undefined): CrawlerDetail | null {
  if (!crawlerName) return null
  
  // 规范化名称（转小写，移除版本号）
  const normalized = crawlerName.toLowerCase().replace(/[\s_-]/g, '').replace(/\/.*$/, '')
  
  // 直接匹配
  if (CRAWLER_DETAILS[normalized]) {
    return CRAWLER_DETAILS[normalized]
  }
  
  // 模糊匹配（处理变体）
  for (const [key, detail] of Object.entries(CRAWLER_DETAILS)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return detail
    }
  }
  
  return null
}

/**
 * 子分类显示标签
 */
export const SUBCATEGORY_LABELS: Record<string, string> = {
  web_search: '网页搜索',
  image_search: '图片搜索',
  video_search: '视频搜索',
  news_search: '新闻搜索',
  mobile_search: '移动搜索',
  page_preview: '页面预览',
  
  ad_quality: '广告质量检查',
  ad_quality_mobile: '移动广告检查',
  ad_indexing: '广告索引',
  contextual_ads: '上下文广告',
  
  ai_training: 'AI训练数据',
  browsing: 'AI联网浏览',
  search_indexing: 'AI搜索索引',
  
  link_preview: '链接预览',
  
  seo_tool: 'SEO工具',
  seo_analysis: 'SEO分析',
  backlink_analysis: '外链分析',
  link_intelligence: '链接智能',
  seo_metrics: 'SEO指标',
  site_auditing: '网站审计',
  
  text_to_speech: '语音朗读',
  rss_atom: 'RSS订阅',
  site_ownership: '所有权验证',
  page_optimization: '页面优化',
  
  product_indexing: '商品索引',
  web_archiving: '网页存档',
  dataset_building: '数据集构建',
  synthetic_monitoring: '综合监控',
  uptime_monitoring: '在线监控'
}

/**
 * 获取子分类标签
 */
export function getSubcategoryLabel(subcategory: string): string {
  return SUBCATEGORY_LABELS[subcategory] || subcategory
}

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
  /** 图标（emoji 或 iconify 图标名） */
  icon: string
  /** 厂商 logo（iconify 图标名，优先显示） */
  vendorIcon?: string
  /** 文档链接 */
  docUrl?: string
}

/**
 * 厂商 → iconify 图标映射
 * 使用彩色品牌 logo，让用户一眼识别厂商
 */
export const VENDOR_ICONS: Record<string, string> = {
  google: 'logos:google-icon',
  bing: 'logos:bing',
  microsoft: 'logos:microsoft-icon',
  openai: 'simple-icons:openai',
  anthropic: 'simple-icons:anthropic',
  baidu: 'simple-icons:baidu',
  facebook: 'logos:facebook',
  bytedance: 'simple-icons:tiktok',
  apple: 'logos:apple',
  yandex: 'logos:yandex',
  duckduckgo: 'logos:duckduckgo',
  slack: 'logos:slack-icon',
  twitter: 'logos:twitter',
  linkedin: 'logos:linkedin-icon',
  telegram: 'logos:telegram',
  amazon: 'logos:aws',
  semrush: 'simple-icons:semrush',
  ahrefs: 'simple-icons:ahrefs',
  majestic: 'simple-icons:majestic',
  moz: 'simple-icons:moz',
  internetarchive: 'simple-icons:internetarchive',
  commoncrawl: 'simple-icons:commoncrawl',
  datadog: 'logos:datadog',
  pingdom: 'simple-icons:pingdom',
  uptimerobot: 'simple-icons:uptimerobot',
  screamingfrog: 'simple-icons:screamingfrog',
  // HTTP 客户端与库
  encode: 'simple-icons:python',
  psf: 'simple-icons:python',
  'aio-libs': 'simple-icons:python',
  python: 'simple-icons:python',
  haxx: 'simple-icons:curl',
  gnu: 'simple-icons:gnu',
  axios: 'simple-icons:axios',
  nodejs: 'logos:nodejs-icon',
  sindresorhus: 'logos:nodejs-icon',
  ladjs: 'logos:nodejs-icon',
  golang: 'logos:go',
  oracle: 'logos:java',
  apache: 'logos:apache',
  square: 'simple-icons:square',
  restsharp: 'simple-icons:dotnet',
  postman: 'logos:postman-icon',
  kong: 'simple-icons:insomnia',
  grafana: 'logos:grafana',
  scrapy: 'simple-icons:scrapy',
  crummy: 'simple-icons:python',
  selenium: 'logos:selenium',
  cypress: 'logos:cypress-icon',
  httpie: 'simple-icons:httpie'
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
  },

  // ========== HTTP 客户端库 ==========
  'pythonhttpx': {
    displayName: 'Python httpx',
    vendor: 'encode',
    vendorName: 'Encode',
    category: 'library',
    subcategory: 'http_client',
    product: 'httpx',
    purpose: 'Python 异步 HTTP 客户端库',
    icon: '🐍',
    docUrl: 'https://www.python-httpx.org/'
  },
  'pythonrequests': {
    displayName: 'Python Requests',
    vendor: 'psf',
    vendorName: 'Python Software Foundation',
    category: 'library',
    subcategory: 'http_client',
    product: 'requests',
    purpose: 'Python HTTP 请求库',
    icon: '🐍',
    docUrl: 'https://requests.readthedocs.io/'
  },
  'pythonaiohttp': {
    displayName: 'Python aiohttp',
    vendor: 'aio-libs',
    vendorName: 'aio-libs',
    category: 'library',
    subcategory: 'http_client',
    product: 'aiohttp',
    purpose: 'Python 异步 HTTP 框架',
    icon: '🐍',
    docUrl: 'https://docs.aiohttp.org/'
  },
  'pythonurllib': {
    displayName: 'Python urllib',
    vendor: 'python',
    vendorName: 'Python',
    category: 'library',
    subcategory: 'http_client',
    product: 'urllib',
    purpose: 'Python 标准库 HTTP 模块',
    icon: '🐍'
  },
  'curl': {
    displayName: 'cURL',
    vendor: 'haxx',
    vendorName: 'Haxx',
    category: 'library',
    subcategory: 'http_client',
    product: 'cURL',
    purpose: '命令行 HTTP 工具',
    icon: '🔧',
    docUrl: 'https://curl.se/'
  },
  'wget': {
    displayName: 'Wget',
    vendor: 'gnu',
    vendorName: 'GNU',
    category: 'library',
    subcategory: 'http_client',
    product: 'Wget',
    purpose: '命令行下载工具',
    icon: '📥',
    docUrl: 'https://www.gnu.org/software/wget/'
  },
  'axios': {
    displayName: 'Axios',
    vendor: 'axios',
    vendorName: 'Axios',
    category: 'library',
    subcategory: 'http_client',
    product: 'axios',
    purpose: 'JavaScript HTTP 客户端库',
    icon: '📦',
    docUrl: 'https://axios-http.com/'
  },
  'nodeaxios': {
    displayName: 'Node.js Axios',
    vendor: 'axios',
    vendorName: 'Axios',
    category: 'library',
    subcategory: 'http_client',
    product: 'axios',
    purpose: 'Node.js HTTP 客户端',
    icon: '🟢',
    docUrl: 'https://axios-http.com/'
  },
  'nodefetch': {
    displayName: 'node-fetch',
    vendor: 'nodejs',
    vendorName: 'Node.js',
    category: 'library',
    subcategory: 'http_client',
    product: 'node-fetch',
    purpose: 'Node.js Fetch API 实现',
    icon: '🟢',
    docUrl: 'https://github.com/node-fetch/node-fetch'
  },
  'got': {
    displayName: 'Got',
    vendor: 'sindresorhus',
    vendorName: 'Sindre Sorhus',
    category: 'library',
    subcategory: 'http_client',
    product: 'got',
    purpose: 'Node.js HTTP 请求库',
    icon: '🟢',
    docUrl: 'https://github.com/sindresorhus/got'
  },
  'superagent': {
    displayName: 'SuperAgent',
    vendor: 'ladjs',
    vendorName: 'Lad',
    category: 'library',
    subcategory: 'http_client',
    product: 'superagent',
    purpose: 'JavaScript HTTP 客户端',
    icon: '🦸',
    docUrl: 'https://ladjs.github.io/superagent/'
  },
  'gohttpclient': {
    displayName: 'Go HTTP Client',
    vendor: 'golang',
    vendorName: 'Go',
    category: 'library',
    subcategory: 'http_client',
    product: 'net/http',
    purpose: 'Go 标准库 HTTP 客户端',
    icon: '🐹'
  },
  'javahttpclient': {
    displayName: 'Java HttpClient',
    vendor: 'oracle',
    vendorName: 'Oracle',
    category: 'library',
    subcategory: 'http_client',
    product: 'java.net.http',
    purpose: 'Java 标准库 HTTP 客户端',
    icon: '☕'
  },
  'apachehttpclient': {
    displayName: 'Apache HttpClient',
    vendor: 'apache',
    vendorName: 'Apache',
    category: 'library',
    subcategory: 'http_client',
    product: 'HttpClient',
    purpose: 'Apache HTTP 客户端库',
    icon: '🪶',
    docUrl: 'https://hc.apache.org/httpcomponents-client-5.2.x/'
  },
  'okhttp': {
    displayName: 'OkHttp',
    vendor: 'square',
    vendorName: 'Square',
    category: 'library',
    subcategory: 'http_client',
    product: 'OkHttp',
    purpose: 'Android/Java HTTP 客户端',
    icon: '🤖',
    docUrl: 'https://square.github.io/okhttp/'
  },
  'restsharp': {
    displayName: 'RestSharp',
    vendor: 'restsharp',
    vendorName: 'RestSharp',
    category: 'library',
    subcategory: 'http_client',
    product: 'RestSharp',
    purpose: '.NET REST 客户端库',
    icon: '🔷',
    docUrl: 'https://restsharp.dev/'
  },
  'httpclient': {
    displayName: 'HttpClient',
    vendor: 'microsoft',
    vendorName: 'Microsoft',
    category: 'library',
    subcategory: 'http_client',
    product: 'HttpClient',
    purpose: '.NET HTTP 客户端',
    icon: '🔷'
  },

  // ========== 测试工具 ==========
  'postman': {
    displayName: 'Postman Runtime',
    vendor: 'postman',
    vendorName: 'Postman',
    category: 'testing',
    subcategory: 'api_testing',
    product: 'Postman',
    purpose: 'API 测试工具',
    icon: '🚀',
    docUrl: 'https://www.postman.com/'
  },
  'insomnia': {
    displayName: 'Insomnia',
    vendor: 'kong',
    vendorName: 'Kong',
    category: 'testing',
    subcategory: 'api_testing',
    product: 'Insomnia',
    purpose: 'REST/GraphQL 客户端',
    icon: '💤',
    docUrl: 'https://insomnia.rest/'
  },
  'jmeter': {
    displayName: 'Apache JMeter',
    vendor: 'apache',
    vendorName: 'Apache',
    category: 'testing',
    subcategory: 'load_testing',
    product: 'JMeter',
    purpose: '性能和负载测试',
    icon: '⚡',
    docUrl: 'https://jmeter.apache.org/'
  },
  'k6': {
    displayName: 'k6',
    vendor: 'grafana',
    vendorName: 'Grafana Labs',
    category: 'testing',
    subcategory: 'load_testing',
    product: 'k6',
    purpose: '现代化负载测试工具',
    icon: '📊',
    docUrl: 'https://k6.io/'
  },

  // ========== 爬虫框架 ==========
  'scrapy': {
    displayName: 'Scrapy',
    vendor: 'scrapy',
    vendorName: 'Scrapy',
    category: 'scraping_framework',
    subcategory: 'web_scraping',
    product: 'Scrapy',
    purpose: 'Python 爬虫框架',
    icon: '🕷️',
    docUrl: 'https://scrapy.org/'
  },
  'beautifulsoup': {
    displayName: 'Beautiful Soup',
    vendor: 'crummy',
    vendorName: 'Leonard Richardson',
    category: 'scraping_framework',
    subcategory: 'html_parser',
    product: 'Beautiful Soup',
    purpose: 'Python HTML 解析库',
    icon: '🍜',
    docUrl: 'https://www.crummy.com/software/BeautifulSoup/'
  },
  'selenium': {
    displayName: 'Selenium',
    vendor: 'selenium',
    vendorName: 'Selenium',
    category: 'testing',
    subcategory: 'browser_automation',
    product: 'Selenium WebDriver',
    purpose: '浏览器自动化测试',
    icon: '🌐',
    docUrl: 'https://www.selenium.dev/'
  },
  'puppeteer': {
    displayName: 'Puppeteer',
    vendor: 'google',
    vendorName: 'Google',
    category: 'testing',
    subcategory: 'browser_automation',
    product: 'Puppeteer',
    purpose: 'Chrome 无头浏览器控制',
    icon: '🎭',
    docUrl: 'https://pptr.dev/'
  },
  'playwright': {
    displayName: 'Playwright',
    vendor: 'microsoft',
    vendorName: 'Microsoft',
    category: 'testing',
    subcategory: 'browser_automation',
    product: 'Playwright',
    purpose: '跨浏览器自动化测试',
    icon: '🎬',
    docUrl: 'https://playwright.dev/'
  },
  'cypress': {
    displayName: 'Cypress',
    vendor: 'cypress',
    vendorName: 'Cypress.io',
    category: 'testing',
    subcategory: 'e2e_testing',
    product: 'Cypress',
    purpose: '前端端到端测试',
    icon: '🌲',
    docUrl: 'https://www.cypress.io/'
  },

  // ========== 其他工具 ==========
  'httpsnoopapi': {
    displayName: 'HttpSnoopAPI',
    vendor: 'unknown',
    vendorName: '未知',
    category: 'monitoring',
    subcategory: 'http_debugging',
    product: 'HTTP Snoop',
    purpose: 'HTTP 调试工具',
    icon: '🔍'
  },
  'httpie': {
    displayName: 'HTTPie',
    vendor: 'httpie',
    vendorName: 'HTTPie',
    category: 'library',
    subcategory: 'http_client',
    product: 'HTTPie',
    purpose: '现代化命令行 HTTP 客户端',
    icon: '🥧',
    docUrl: 'https://httpie.io/'
  }
}

/**
 * 根据 crawler_name 获取详细信息
 */
export function getCrawlerDetail(crawlerName: string | null | undefined): CrawlerDetail | null {
  if (!crawlerName) return null
  
  // 规范化名称（转小写，移除版本号和特殊字符）
  const normalized = crawlerName.toLowerCase().replace(/[\s_-]/g, '').replace(/\/.*$/, '')
  
  // 1. 直接精确匹配
  if (CRAWLER_DETAILS[normalized]) {
    return CRAWLER_DETAILS[normalized]
  }
  
  // 2. 智能识别规则（处理常见模式）
  // Python 生态：python-xxx、python/xxx
  if (normalized.startsWith('python')) {
    const pythonLib = normalized.replace(/^python/, '')
    if (CRAWLER_DETAILS[`python${pythonLib}`]) {
      return CRAWLER_DETAILS[`python${pythonLib}`]
    }
    // 通用 Python 库兜底
    if (pythonLib && pythonLib.length >= 3) {
      return {
        displayName: `Python ${crawlerName.split(/[-_/]/)[1] || crawlerName}`,
        vendor: 'python',
        vendorName: 'Python',
        category: 'library',
        subcategory: 'http_client',
        product: pythonLib,
        purpose: 'Python HTTP 客户端库',
        icon: '🐍'
      }
    }
  }
  
  // Node.js 生态：node-xxx、node/xxx
  if (normalized.startsWith('node')) {
    const nodeLib = normalized.replace(/^node/, '')
    if (CRAWLER_DETAILS[`node${nodeLib}`]) {
      return CRAWLER_DETAILS[`node${nodeLib}`]
    }
    // 通用 Node.js 库兜底
    if (nodeLib && nodeLib.length >= 3) {
      return {
        displayName: `Node.js ${crawlerName.split(/[-_/]/)[1] || crawlerName}`,
        vendor: 'nodejs',
        vendorName: 'Node.js',
        category: 'library',
        subcategory: 'http_client',
        product: nodeLib,
        purpose: 'Node.js HTTP 客户端库',
        icon: '🟢'
      }
    }
  }
  
  // Go 生态：go-xxx、golang-xxx
  if (normalized.startsWith('go') || normalized.startsWith('golang')) {
    return {
      displayName: `Go ${crawlerName}`,
      vendor: 'golang',
      vendorName: 'Go',
      category: 'library',
      subcategory: 'http_client',
      product: crawlerName,
      purpose: 'Go HTTP 客户端库',
      icon: '🐹'
    }
  }
  
  // Java 生态：java-xxx
  if (normalized.startsWith('java')) {
    return {
      displayName: `Java ${crawlerName}`,
      vendor: 'oracle',
      vendorName: 'Java',
      category: 'library',
      subcategory: 'http_client',
      product: crawlerName,
      purpose: 'Java HTTP 客户端库',
      icon: '☕'
    }
  }
  
  // 3. 模糊匹配（处理变体）
  // 仅保留“爬虫名称包含已知特征词”这一方向的匹配，避免反向匹配导致
  // 短词（如通用兜底提取出的 "bot"）被误判为任意包含该子串的具体厂商
  // （例如 "bot" 会被 "googlebot" 误命中），详见访问日志爬虫识别误判问题。
  // 同时要求已知特征词长度达到一定阈值，进一步降低短词误伤风险。
  for (const [key, detail] of Object.entries(CRAWLER_DETAILS)) {
    if (key.length >= 5 && normalized.includes(key)) {
      return detail
    }
  }
  
  return null
}

/**
 * 根据 vendor 获取厂商 iconify 图标名
 * 找不到时返回通用机器人图标
 */
export function getVendorIcon(vendor?: string | null): string {
  if (!vendor) return 'mdi:robot-outline'
  return VENDOR_ICONS[vendor.toLowerCase()] || 'mdi:robot-outline'
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
  uptime_monitoring: '在线监控',

  // HTTP 客户端与测试工具
  http_client: 'HTTP 客户端',
  http_debugging: 'HTTP 调试',
  api_testing: 'API 测试',
  load_testing: '负载测试',
  e2e_testing: '端到端测试',
  browser_automation: '浏览器自动化',
  web_scraping: '网页抓取',
  html_parser: 'HTML 解析'
}

/**
 * 获取子分类标签
 */
export function getSubcategoryLabel(subcategory: string): string {
  return SUBCATEGORY_LABELS[subcategory] || subcategory
}

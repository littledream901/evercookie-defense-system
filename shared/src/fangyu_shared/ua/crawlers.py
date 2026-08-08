"""知名爬虫/机器人厂商特征库。

设计取舍：
- 纯数据 + 正则，零外部依赖，避免引入 user-agents / ua-parser 等重量级包；
- 按「厂商」而非「单个 UA」组织，便于规则里按 ua.crawler_vendor 精准放行或拦截；
- category 用于粗粒度策略（例如放行 search_engine、拦截 ai_crawler）。

category 取值：
  search_engine  搜索引擎（通常应放行，影响 SEO）
  social         社交平台预览抓取（分享卡片依赖）
  ai_crawler     AI 语料抓取（多数站点希望限流或拦截）
  seo            商业 SEO 分析工具（通常限流）
  monitoring     可用性监控（自建的应加白名单）
  security       安全扫描/攻击工具（应拦截）
  library        通用 HTTP 客户端/脚本库（视业务而定）
  feed           RSS/订阅抓取
  archive        归档爬虫
  other          已识别为 bot 但归类不明
"""

from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class CrawlerSignature:
    """单条爬虫特征。"""

    vendor: str
    category: str
    pattern: re.Pattern[str]
    verifiable: bool = False
    """厂商是否提供反查 DNS 校验（Google/Bing 等），供后续 PTR 验证扩展使用。"""
    name_pattern: re.Pattern[str] | None = None
    """用于从UA中提取具体爬虫名称的正则（如"Googlebot"、"Bingbot"）"""


def _sig(vendor: str, category: str, raw: str, *, verifiable: bool = False, name_pattern: str | None = None) -> CrawlerSignature:
    return CrawlerSignature(
        vendor=vendor,
        category=category,
        pattern=re.compile(raw, re.IGNORECASE),
        verifiable=verifiable,
        name_pattern=re.compile(name_pattern, re.IGNORECASE) if name_pattern else None,
    )


_SEARCH_ENGINE: tuple[CrawlerSignature, ...] = (
    _sig("google", "search_engine", r"\b(?:googlebot|googlebot-image|googlebot-news|googlebot-video|google-inspectiontool|googleother|storebot-google|adsbot-google|mediapartners-google|feedfetcher-google|apis-google)\b", verifiable=True, name_pattern=r"(?:googlebot-image|googlebot-news|googlebot-video|googlebot|adsbot-google|mediapartners-google|feedfetcher-google|storebot-google|google-inspectiontool|googleother|apis-google)(?:/[\d.]+)?"),
    _sig("bing", "search_engine", r"\b(?:bingbot|adidxbot|bingpreview|msnbot|microsoftpreview)\b", verifiable=True, name_pattern=r"(?:bingbot|adidxbot|bingpreview|msnbot|microsoftpreview)(?:/[\d.]+)?"),
    _sig("baidu", "search_engine", r"\b(?:baiduspider|baiduspider-render|baiduspider-image)\b", verifiable=True, name_pattern=r"(?:baiduspider-render|baiduspider-image|baiduspider)(?:/[\d.]+)?"),
    _sig("yandex", "search_engine", r"\b(?:yandexbot|yandeximages|yandexmobilebot|yandexaccessibilitybot|yandexrenderresourcesbot)\b", verifiable=True, name_pattern=r"(?:yandexrenderresourcesbot|yandexaccessibilitybot|yandexmobilebot|yandeximages|yandexbot)(?:/[\d.]+)?"),
    _sig("duckduckgo", "search_engine", r"\b(?:duckduckbot|duckduckgo-favicons-bot|duckassistbot)\b", verifiable=True),
    _sig("sogou", "search_engine", r"\bsogou\s?(?:web|inst|pic|news|video|orion)?\s?spider\b"),
    _sig("360", "search_engine", r"\b(?:360spider|haosouspider|360spider-image)\b"),
    _sig("shenma", "search_engine", r"\b(?:yisouspider|shenmaspider)\b"),
    _sig("bytedance", "search_engine", r"\btoutiaospider\b"),
    _sig("naver", "search_engine", r"\b(?:yeti|naverbot)\b"),
    _sig("seznam", "search_engine", r"\bseznambot\b"),
    _sig("qwant", "search_engine", r"\bqwantify|qwantbot\b"),
    _sig("mojeek", "search_engine", r"\bmojeekbot\b"),
    _sig("brave", "search_engine", r"\bbravebot\b"),
    _sig("petal", "search_engine", r"\bpetalbot\b"),
    _sig("coccoc", "search_engine", r"\bcoccocbot\b"),
    _sig("exalead", "search_engine", r"\bexabot\b"),
    _sig("apple", "search_engine", r"\bapplebot\b(?!-extended)", verifiable=True),
)

_SOCIAL: tuple[CrawlerSignature, ...] = (
    _sig("meta", "social", r"\b(?:facebookexternalhit|facebookcatalog|facebookbot|meta-externalagent|meta-externalfetcher)\b"),
    _sig("twitter", "social", r"\btwitterbot\b"),
    _sig("linkedin", "social", r"\blinkedinbot\b"),
    _sig("pinterest", "social", r"\bpinterest(?:bot|/\d)\b"),
    _sig("slack", "social", r"\b(?:slackbot|slack-imgproxy)\b"),
    _sig("discord", "social", r"\bdiscordbot\b"),
    _sig("telegram", "social", r"\btelegrambot\b"),
    _sig("whatsapp", "social", r"\bwhatsapp/\d"),
    _sig("reddit", "social", r"\bredditbot\b"),
    _sig("tencent", "social", r"\b(?:qq(?:browser)? ?bot|micromessenger ?bot|wechat-bot)\b"),
    _sig("weibo", "social", r"\bweibo(?:bot|spider)\b"),
    _sig("tumblr", "social", r"\btumblr\b"),
    _sig("vk", "social", r"\bvkshare\b"),
    _sig("skype", "social", r"\bskypeuripreview\b"),
    _sig("embedly", "social", r"\bembedly\b"),
    _sig("iframely", "social", r"\biframely\b"),
)

_AI_CRAWLER: tuple[CrawlerSignature, ...] = (
    _sig("openai", "ai_crawler", r"\b(?:gptbot|chatgpt-user|oai-searchbot)\b"),
    _sig("anthropic", "ai_crawler", r"\b(?:claudebot|claude-web|anthropic-ai|claude-searchbot|claude-user)\b"),
    _sig("google", "ai_crawler", r"\b(?:google-extended|google-cloudvertexbot)\b"),
    _sig("apple", "ai_crawler", r"\bapplebot-extended\b"),
    _sig("commoncrawl", "ai_crawler", r"\bccbot\b"),
    _sig("perplexity", "ai_crawler", r"\b(?:perplexitybot|perplexity-user)\b"),
    _sig("bytedance", "ai_crawler", r"\b(?:bytespider|tiktokspider)\b"),
    _sig("amazon", "ai_crawler", r"\bamazonbot\b"),
    _sig("meta", "ai_crawler", r"\bfacebookbot\b"),
    _sig("cohere", "ai_crawler", r"\bcohere-ai|cohere-training-data-crawler\b"),
    _sig("ai2", "ai_crawler", r"\bai2bot\b"),
    _sig("diffbot", "ai_crawler", r"\bdiffbot\b"),
    _sig("timpi", "ai_crawler", r"\btimpibot\b"),
    _sig("omgili", "ai_crawler", r"\bomgili(?:bot)?\b"),
    _sig("youbot", "ai_crawler", r"\byoubot\b"),
    _sig("mistral", "ai_crawler", r"\bmistralai-user\b"),
    _sig("huggingface", "ai_crawler", r"\bimagesiftbot\b"),
)

_SEO: tuple[CrawlerSignature, ...] = (
    _sig("ahrefs", "seo", r"\bahrefs(?:bot|siteaudit)\b"),
    _sig("semrush", "seo", r"\bsemrush(?:bot)?\b"),
    _sig("majestic", "seo", r"\bmj12bot\b"),
    _sig("moz", "seo", r"\b(?:rogerbot|dotbot)\b"),
    _sig("screamingfrog", "seo", r"\bscreaming frog seo spider\b"),
    _sig("sistrix", "seo", r"\bsistrix\b"),
    _sig("serpstat", "seo", r"\bserpstatbot\b"),
    _sig("dataforseo", "seo", r"\bdataforseobot\b"),
    _sig("seokicks", "seo", r"\bseokicks\b"),
    _sig("barkrowler", "seo", r"\bbarkrowler\b"),
    _sig("blexbot", "seo", r"\bblexbot\b"),
    _sig("linkdex", "seo", r"\blinkdexbot\b"),
    _sig("cocolyze", "seo", r"\bcocolyzebot\b"),
    _sig("zoominfo", "seo", r"\bzoominfobot\b"),
)

_MONITORING: tuple[CrawlerSignature, ...] = (
    _sig("pingdom", "monitoring", r"\bpingdom(?:\.com_bot|tms)?\b"),
    _sig("uptimerobot", "monitoring", r"\buptimerobot\b"),
    _sig("statuscake", "monitoring", r"\bstatuscake\b"),
    _sig("newrelic", "monitoring", r"\bnewrelicpinger\b"),
    _sig("datadog", "monitoring", r"\bdatadog(?:-synthetics|bot)?\b"),
    _sig("site24x7", "monitoring", r"\bsite24x7\b"),
    _sig("gtmetrix", "monitoring", r"\bgtmetrix\b"),
    _sig("lighthouse", "monitoring", r"\b(?:chrome-lighthouse|lighthouse)\b"),
    _sig("betteruptime", "monitoring", r"\bbetter uptime bot\b"),
    _sig("prometheus", "monitoring", r"\b(?:prometheus|blackbox_exporter)\b"),
    _sig("zabbix", "monitoring", r"\bzabbix\b"),
    _sig("cloudflare", "monitoring", r"\b(?:cloudflare-(?:traffic-manager|healthchecks|alwaysonline)|cf-uc)\b"),
    _sig("aws", "monitoring", r"\b(?:elb-healthchecker|amazon cloudfront)\b"),
    _sig("googlecloud", "monitoring", r"\bgooglehc\b"),
    _sig("kubernetes", "monitoring", r"\bkube-probe\b"),
)

_SECURITY: tuple[CrawlerSignature, ...] = (
    _sig("sqlmap", "security", r"\bsqlmap\b"),
    _sig("nikto", "security", r"\bnikto\b"),
    _sig("nessus", "security", r"\bnessus\b"),
    _sig("openvas", "security", r"\b(?:openvas|gvm)\b"),
    _sig("acunetix", "security", r"\bacunetix\b"),
    _sig("nmap", "security", r"\bnmap (?:scripting engine|nse)\b"),
    _sig("masscan", "security", r"\bmasscan\b"),
    _sig("zgrab", "security", r"\b(?:zgrab|zmap)\b"),
    _sig("nuclei", "security", r"\bnuclei\b"),
    _sig("wpscan", "security", r"\bwpscan\b"),
    _sig("dirbuster", "security", r"\b(?:dirbuster|gobuster|feroxbuster|ffuf)\b"),
    _sig("burpsuite", "security", r"\b(?:burp ?suite|burpcollaborator)\b"),
    _sig("zaproxy", "security", r"\b(?:zaproxy|owasp zap)\b"),
    _sig("metasploit", "security", r"\bmetasploit\b"),
    _sig("hydra", "security", r"\b(?:thc-hydra|hydra)\b"),
    _sig("xrumer", "security", r"\b(?:xrumer|gsa search engine ranker)\b"),
    _sig("censys", "security", r"\bcensysinspect\b"),
    _sig("shodan", "security", r"\bshodan\b"),
    _sig("internetmeasurement", "security", r"\binternet-measurement\.com\b"),
    _sig("paloalto", "security", r"\bexpanse(?:, a palo alto networks company)?\b"),
)

_LIBRARY: tuple[CrawlerSignature, ...] = (
    _sig("curl", "library", r"^curl/|\bcurl/\d"),
    _sig("wget", "library", r"\bwget(?:/\d|\b)"),
    _sig("python-requests", "library", r"\bpython-requests\b"),
    _sig("python-urllib", "library", r"\b(?:python-urllib|urllib3)\b"),
    _sig("python-httpx", "library", r"\bpython-httpx\b"),
    _sig("aiohttp", "library", r"\baiohttp\b"),
    _sig("scrapy", "library", r"\bscrapy\b"),
    _sig("go-http", "library", r"\bgo-http-client\b"),
    _sig("java", "library", r"\b(?:java/\d|apache-httpclient|okhttp|jakarta commons-httpclient)\b"),
    _sig("node", "library", r"\b(?:node-fetch|axios|got/\d|undici|superagent)\b"),
    _sig("php", "library", r"\b(?:guzzlehttp|php/\d|wordpress/|drupal)\b"),
    _sig("ruby", "library", r"\b(?:ruby/\d|faraday|typhoeus)\b"),
    _sig("dotnet", "library", r"\b(?:restsharp|dotnet httpclient|httpclient/\d)\b"),
    _sig("rust", "library", r"\breqwest\b"),
    _sig("perl", "library", r"\blibwww-perl\b"),
    _sig("postman", "library", r"\bpostmanruntime\b"),
    _sig("insomnia", "library", r"\binsomnia\b"),
    _sig("httpie", "library", r"\bhttpie\b"),
    _sig("headless-chrome", "library", r"\b(?:headlesschrome|chrome-headless)\b"),
    _sig("puppeteer", "library", r"\bpuppeteer\b"),
    _sig("playwright", "library", r"\bplaywright\b"),
    _sig("selenium", "library", r"\b(?:selenium|webdriver)\b"),
    _sig("phantomjs", "library", r"\bphantomjs\b"),
)

_FEED: tuple[CrawlerSignature, ...] = (
    _sig("feedly", "feed", r"\bfeedly(?:bot|app)?\b"),
    _sig("inoreader", "feed", r"\binoreader\b"),
    _sig("newsblur", "feed", r"\bnewsblur\b"),
    _sig("feedburner", "feed", r"\bfeedburner\b"),
    _sig("theoldreader", "feed", r"\btheoldreader\b"),
    _sig("tinytinyrss", "feed", r"\btt-rss\b"),
    _sig("rssbot", "feed", r"\b(?:rss ?bot|simplepie|universalfeedparser)\b"),
)

_ARCHIVE: tuple[CrawlerSignature, ...] = (
    _sig("internetarchive", "archive", r"\b(?:ia_archiver|archive\.org_bot|wayback)\b"),
    _sig("commoncrawl", "archive", r"\bccbot\b"),
    _sig("heritrix", "archive", r"\bheritrix\b"),
    _sig("httrack", "archive", r"\bhttrack\b"),
    _sig("webcopier", "archive", r"\b(?:webcopier|webzip|teleport ?pro|offline explorer)\b"),
)

CRAWLER_SIGNATURES: tuple[CrawlerSignature, ...] = (
    *_SECURITY,
    *_AI_CRAWLER,
    *_SEARCH_ENGINE,
    *_SOCIAL,
    *_SEO,
    *_MONITORING,
    *_FEED,
    *_ARCHIVE,
    *_LIBRARY,
)
"""按优先级排列的爬虫特征表。

顺序即匹配优先级：
1. security 最先，避免攻击工具伪装成其他类别被放过；
2. ai_crawler 在 search_engine 之前，因为部分厂商（Google/Apple）同时拥有两类 UA，
   带 -Extended / -CloudVertexBot 后缀的必须先被 AI 分类命中；
3. library 最后，因为 "Java/1.8" 这类弱特征容易误伤真实客户端。
"""

_GENERIC_BOT_RE = re.compile(
    r"\b(?:bot|spider|crawler|crawl|slurp|scraper|fetcher|scanner|checker|monitor|probe|indexer)\b",
    re.IGNORECASE,
)


def match_crawler(user_agent: str) -> CrawlerSignature | None:
    """按优先级匹配已知爬虫厂商，未命中则回退通用 bot 关键词。"""
    if not user_agent:
        return None
    for sig in CRAWLER_SIGNATURES:
        if sig.pattern.search(user_agent):
            return sig
    if _GENERIC_BOT_RE.search(user_agent):
        return CrawlerSignature(vendor="unknown", category="other", pattern=_GENERIC_BOT_RE)
    return None


def extract_crawler_name(user_agent: str, signature: CrawlerSignature | None) -> str | None:
    """从UA字符串中提取具体的爬虫名称（如"Googlebot"、"Bingbot"）。"""
    if not user_agent or not signature:
        return None
    
    # 如果签名提供了name_pattern，使用它
    if signature.name_pattern:
        match = signature.name_pattern.search(user_agent)
        if match:
            return match.group(0)
    
    # 否则使用主pattern提取
    match = signature.pattern.search(user_agent)
    if match:
        # 返回匹配到的完整词（去除非字母数字字符）
        matched = match.group(0).strip()
        return matched if matched else None
    
    return None


CRAWLER_CATEGORIES: frozenset[str] = frozenset(
    {
        "search_engine",
        "social",
        "ai_crawler",
        "seo",
        "monitoring",
        "security",
        "library",
        "feed",
        "archive",
        "other",
    }
)

CRAWLER_VENDORS: frozenset[str] = frozenset(sig.vendor for sig in CRAWLER_SIGNATURES)

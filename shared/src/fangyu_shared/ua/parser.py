"""User-Agent 解析器（纯正则，零外部依赖）。

输出字段设计为可直接被规则条件引用（ua.device_type / ua.os / ua.brand ...），
解析结果带 LRU 缓存，同一 UA 字符串在高 QPS 下只解析一次。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

from fangyu_shared.ua.crawlers import match_crawler, extract_crawler_name

DEVICE_TYPES: frozenset[str] = frozenset({"desktop", "mobile", "tablet", "bot", "tv", "console", "wearable", "unknown"})

CLIENT_TYPES: frozenset[str] = frozenset({"browser", "app", "library", "bot", "unknown"})


@dataclass(frozen=True, slots=True)
class UAResult:
    """UA 解析结果。字段名即规则里 ua.* 的路径名。"""

    device_type: str = "unknown"
    os: str = "unknown"
    os_version: str | None = None
    browser: str = "unknown"
    browser_version: str | None = None
    engine: str = "unknown"
    brand: str = "unknown"
    model: str | None = None
    client_type: str = "unknown"
    client_name: str = "unknown"
    is_bot: bool = False
    is_mobile: bool = False
    crawler_name: str | None = None
    crawler_category: str | None = None
    crawler_vendor: str | None = None
    crawler_verifiable: bool = False
    is_empty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


UNKNOWN_UA = UAResult(is_empty=True, device_type="unknown", client_type="unknown")


_WINDOWS_NT_MAP = {
    "10.0": "10",
    "6.3": "8.1",
    "6.2": "8",
    "6.1": "7",
    "6.0": "Vista",
    "5.2": "XP",
    "5.1": "XP",
}

_OS_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("harmonyos", re.compile(r"harmonyos(?:[ /](?P<v>[\d._]+))?", re.I)),
    ("android", re.compile(r"android[ /](?P<v>[\d._]+)", re.I)),
    ("android", re.compile(r"\bandroid\b", re.I)),
    ("ios", re.compile(r"\b(?:iphone|ipad|ipod)(?:.*?)os (?P<v>[\d_]+)", re.I)),
    ("ios", re.compile(r"\b(?:iphone|ipad|ipod)\b", re.I)),
    ("macos", re.compile(r"mac os x (?P<v>[\d_.]+)", re.I)),
    ("macos", re.compile(r"\b(?:macintosh|mac os x)\b", re.I)),
    ("chromeos", re.compile(r"\bcros\b(?:[ \w]*?)(?P<v>[\d.]+)?", re.I)),
    ("windows_phone", re.compile(r"windows phone(?: os)? (?P<v>[\d.]+)", re.I)),
    ("windows", re.compile(r"windows nt (?P<v>[\d.]+)", re.I)),
    ("windows", re.compile(r"\bwin(?:dows|16|32|64)\b", re.I)),
    ("ubuntu", re.compile(r"\bubuntu\b", re.I)),
    ("debian", re.compile(r"\bdebian\b", re.I)),
    ("centos", re.compile(r"\bcentos\b", re.I)),
    ("fedora", re.compile(r"\bfedora\b", re.I)),
    ("freebsd", re.compile(r"\bfreebsd\b", re.I)),
    ("linux", re.compile(r"\b(?:linux|x11)\b", re.I)),
)


def _parse_os(ua: str) -> tuple[str, str | None]:
    for name, pattern in _OS_RULES:
        m = pattern.search(ua)
        if not m:
            continue
        version: str | None = None
        if "v" in m.groupdict():
            raw = m.group("v")
            if raw:
                version = raw.replace("_", ".")
        if name == "windows" and version:
            version = _WINDOWS_NT_MAP.get(version, version)
        return name, version
    return "unknown", None


_BROWSER_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("micromessenger", "app", re.compile(r"micromessenger/(?P<v>[\d.]+)", re.I)),
    ("wechat_devtools", "app", re.compile(r"wechatdevtools", re.I)),
    ("alipay", "app", re.compile(r"alipayclient/(?P<v>[\d.]+)", re.I)),
    ("dingtalk", "app", re.compile(r"dingtalk/(?P<v>[\d.]+)", re.I)),
    ("feishu", "app", re.compile(r"(?:feishu|lark)/(?P<v>[\d.]+)", re.I)),
    ("qq", "app", re.compile(r"\bqq/(?P<v>[\d.]+)", re.I)),
    ("weibo", "app", re.compile(r"weibo(?:__)?(?P<v>[\d.]+)?", re.I)),
    ("douyin", "app", re.compile(r"aweme|\bdouyin\b", re.I)),
    ("tiktok", "app", re.compile(r"\btrill\b|musical_ly", re.I)),
    ("baiduapp", "app", re.compile(r"baiduboxapp/(?P<v>[\d.]+)", re.I)),
    ("quark", "browser", re.compile(r"quark/(?P<v>[\d.]+)", re.I)),
    ("ucbrowser", "browser", re.compile(r"(?:ucbrowser|ubrowser)/(?P<v>[\d.]+)", re.I)),
    ("qqbrowser", "browser", re.compile(r"(?:qqbrowser|mqqbrowser)/(?P<v>[\d.]+)", re.I)),
    ("2345explorer", "browser", re.compile(r"2345explorer/(?P<v>[\d.]+)", re.I)),
    ("maxthon", "browser", re.compile(r"maxthon/(?P<v>[\d.]+)", re.I)),
    ("miuibrowser", "browser", re.compile(r"miuibrowser/(?P<v>[\d.]+)", re.I)),
    ("huaweibrowser", "browser", re.compile(r"huaweibrowser/(?P<v>[\d.]+)", re.I)),
    ("heytapbrowser", "browser", re.compile(r"heytapbrowser/(?P<v>[\d.]+)", re.I)),
    ("vivobrowser", "browser", re.compile(r"vivobrowser/(?P<v>[\d.]+)", re.I)),
    ("samsungbrowser", "browser", re.compile(r"samsungbrowser/(?P<v>[\d.]+)", re.I)),
    ("yandexbrowser", "browser", re.compile(r"yabrowser/(?P<v>[\d.]+)", re.I)),
    ("brave", "browser", re.compile(r"\bbrave/(?P<v>[\d.]+)", re.I)),
    ("vivaldi", "browser", re.compile(r"vivaldi/(?P<v>[\d.]+)", re.I)),
    ("opera", "browser", re.compile(r"(?:opr|opera|opios|opt)/(?P<v>[\d.]+)", re.I)),
    ("edge", "browser", re.compile(r"(?:edge|edg|edga|edgios)/(?P<v>[\d.]+)", re.I)),
    ("firefox", "browser", re.compile(r"(?:firefox|fxios)/(?P<v>[\d.]+)", re.I)),
    ("chrome", "browser", re.compile(r"(?:chrome|crios|chromium)/(?P<v>[\d.]+)", re.I)),
    ("safari", "browser", re.compile(r"version/(?P<v>[\d.]+).*\bsafari\b", re.I)),
    ("ie", "browser", re.compile(r"(?:msie |trident/.*rv:)(?P<v>[\d.]+)", re.I)),
    ("webview", "app", re.compile(r"\bwv\b|; wv\)", re.I)),
)


def _parse_browser(ua: str) -> tuple[str, str | None, str]:
    """返回 (browser, version, client_type)。"""
    for name, client_type, pattern in _BROWSER_RULES:
        m = pattern.search(ua)
        if not m:
            continue
        version = m.group("v") if "v" in m.groupdict() else None
        return name, version, client_type
    return "unknown", None, "unknown"


_ENGINE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("blink", re.compile(r"\b(?:chrome|crios|chromium|edg|opr)/", re.I)),
    ("gecko", re.compile(r"\b(?:firefox|fxios)/", re.I)),
    ("webkit", re.compile(r"applewebkit/", re.I)),
    ("trident", re.compile(r"\btrident/|\bmsie ", re.I)),
    ("presto", re.compile(r"\bpresto/", re.I)),
)


def _parse_engine(ua: str) -> str:
    for name, pattern in _ENGINE_RULES:
        if pattern.search(ua):
            return name
    return "unknown"


_BRAND_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("apple", re.compile(r"\b(?:iphone|ipad|ipod|macintosh|mac os x|apple ?tv|watchos)\b", re.I)),
    ("huawei", re.compile(r"\b(?:huawei|honor|harmonyos|hmscore|\bhw-|ALP-|EML-|VOG-|LIO-|NOH-|ELS-)", re.I)),
    ("xiaomi", re.compile(r"\b(?:xiaomi|redmi|poco|miuibrowser|\bmi \d|mix \d)\b", re.I)),
    ("samsung", re.compile(r"\b(?:samsung|sm-[a-z]\d|gt-[a-z]\d|sch-|shv-)", re.I)),
    ("oppo", re.compile(r"\b(?:oppo|heytapbrowser|realme|\bcph\d{4})", re.I)),
    ("vivo", re.compile(r"\b(?:vivo|vivobrowser|\bv\d{4}[a-z]{1,2})\b", re.I)),
    ("oneplus", re.compile(r"\b(?:oneplus|\bne2\d{3}|\bkb2\d{3})\b", re.I)),
    ("meizu", re.compile(r"\b(?:meizu|m\d{3}[a-z])\b", re.I)),
    ("google", re.compile(r"\b(?:pixel(?: \d[a-z]*)?|nexus \d+)\b", re.I)),
    ("motorola", re.compile(r"\b(?:motorola|moto[ _]?[a-z]?\d*|xt\d{4})\b", re.I)),
    ("nokia", re.compile(r"\bnokia\b", re.I)),
    ("sony", re.compile(r"\b(?:sony|xperia)\b", re.I)),
    ("lg", re.compile(r"\b(?:lg-|lge|lg electronics)\b", re.I)),
    ("htc", re.compile(r"\bhtc\b", re.I)),
    ("zte", re.compile(r"\b(?:zte|nubia)\b", re.I)),
    ("lenovo", re.compile(r"\b(?:lenovo|thinkpad)\b", re.I)),
    ("asus", re.compile(r"\b(?:asus|zenfone)\b", re.I)),
    ("amazon", re.compile(r"\b(?:kindle|kftt|silk/|fire ?(?:tv|tablet))\b", re.I)),
    ("microsoft", re.compile(r"\b(?:surface|xbox|windows phone|lumia)\b", re.I)),
)


def _parse_brand(ua: str) -> str:
    for name, pattern in _BRAND_RULES:
        if pattern.search(ua):
            return name
    return "unknown"


_UA_PAREN_RE = re.compile(r"\(([^)]*)\)")
_ANDROID_VER_TOKEN_RE = re.compile(r"^android[\s/]", re.I)
_LOCALE_TOKEN_RE = re.compile(r"^[a-z]{2}([-_][a-z]{2,4})?$", re.I)
_MODEL_NOISE_TOKENS = frozenset(
    {"linux", "u", "wv", "mobile", "harmonyos", "hmscore", "x11", "compatible", "khtml, like gecko"}
)
_APPLE_MODEL_RE = re.compile(r"\b(?P<model>iphone|ipad|ipod touch|ipod|macintosh)\b", re.I)


def _parse_model(ua: str, os_name: str) -> str | None:
    """从 UA 括号段里提取设备型号。

    Android/HarmonyOS 的括号段形如 `(Linux; Android 13; SM-S918B Build/TP1A)`，
    逐段剔除 OS / 语言 / 噪声 token 后取首个有效段，兼容 HarmonyOS 多出的
    `HarmonyOS; ELS-AN00; HMSCore` 结构。
    """
    if os_name in {"android", "harmonyos"}:
        for block in _UA_PAREN_RE.findall(ua):
            if "android" not in block.lower() and os_name == "android":
                continue
            for raw in block.split(";"):
                token = raw.strip()
                token = re.sub(r"\s*build/.*$", "", token, flags=re.I).strip()
                if not token or len(token) > 64:
                    continue
                lowered = token.lower()
                if lowered in _MODEL_NOISE_TOKENS:
                    continue
                if _ANDROID_VER_TOKEN_RE.match(lowered) or _LOCALE_TOKEN_RE.match(lowered):
                    continue
                return token
        return None
    if os_name in {"ios", "macos"}:
        m = _APPLE_MODEL_RE.search(ua)
        return m.group("model") if m else None
    return None


_TV_RE = re.compile(r"\b(?:smart-?tv|smarttv|googletv|appletv|hbbtv|netcast|viera|roku|tizen|web ?os|crkey)\b", re.I)
_CONSOLE_RE = re.compile(r"\b(?:playstation|xbox|nintendo)\b", re.I)
_WEARABLE_RE = re.compile(r"\b(?:watch(?:os)?|wear ?os|galaxy watch)\b", re.I)
_TABLET_RE = re.compile(r"\b(?:ipad|tablet|kindle|silk/|playbook|nexus (?:7|9|10)|sm-t\d)", re.I)
_MOBILE_RE = re.compile(r"\b(?:mobile|iphone|ipod|windows phone|blackberry|opera mini|iemobile)\b", re.I)
_DESKTOP_OS = frozenset({"windows", "macos", "linux", "chromeos", "ubuntu", "debian", "centos", "fedora", "freebsd"})


def _parse_device_type(ua: str, os_name: str, *, is_bot: bool) -> str:
    if is_bot:
        return "bot"
    if _CONSOLE_RE.search(ua):
        return "console"
    if _TV_RE.search(ua):
        return "tv"
    if _WEARABLE_RE.search(ua):
        return "wearable"
    if _TABLET_RE.search(ua):
        return "tablet"
    if _MOBILE_RE.search(ua):
        return "mobile"
    if os_name in {"android", "harmonyos"}:
        return "tablet"
    if os_name in _DESKTOP_OS:
        return "desktop"
    return "unknown"


_REAL_BROWSER_TOKEN_RE = re.compile(r"\b(?:mozilla/\d|applewebkit/\d|gecko/\d|trident/\d)", re.I)
_WEAK_LIBRARY_VENDORS = frozenset({"java", "node", "php", "ruby", "dotnet", "rust", "perl"})
"""这些库特征在真实客户端 UA 里也可能出现（内嵌 WebView / CMS 转发），需要降级判定。

反之 curl / scrapy / headless-chrome / puppeteer / selenium 等是强 bot 信号，
即使 UA 里伪造了 Mozilla token 也必须保持 is_bot=True。
"""
_MAX_UA_LENGTH = 2048


@lru_cache(maxsize=8192)
def parse_user_agent(user_agent: str | None) -> UAResult:
    """解析 UA 字符串。空 UA 返回 UNKNOWN_UA（is_empty=True）。"""
    if not user_agent or not user_agent.strip():
        return UNKNOWN_UA

    ua = user_agent[:_MAX_UA_LENGTH]

    crawler = match_crawler(ua)
    crawler_name = extract_crawler_name(ua, crawler)
    crawler_category = crawler.category if crawler else None
    crawler_vendor = crawler.vendor if crawler else None

    os_name, os_version = _parse_os(ua)
    browser, browser_version, client_type = _parse_browser(ua)
    engine = _parse_engine(ua)

    is_bot = crawler is not None
    if (
        is_bot
        and crawler_category == "library"
        and crawler_vendor in _WEAK_LIBRARY_VENDORS
        and browser != "unknown"
        and _REAL_BROWSER_TOKEN_RE.search(ua)
    ):
        is_bot = False
        crawler_name = None
        crawler_category = None
        crawler_vendor = None

    device_type = _parse_device_type(ua, os_name, is_bot=is_bot)
    brand = "unknown" if is_bot else _parse_brand(ua)
    model = None if is_bot else _parse_model(ua, os_name)

    if is_bot:
        client_type = "library" if crawler_category == "library" else "bot"
        client_name = crawler_vendor or "unknown"
    else:
        client_name = browser

    return UAResult(
        device_type=device_type,
        os=os_name,
        os_version=os_version,
        browser=browser,
        browser_version=browser_version,
        engine=engine,
        brand=brand,
        model=model,
        client_type=client_type,
        client_name=client_name,
        is_bot=is_bot,
        is_mobile=device_type in {"mobile", "tablet"},
        crawler_name=crawler_name,
        crawler_category=crawler_category,
        crawler_vendor=crawler_vendor,
        crawler_verifiable=bool(crawler and crawler.verifiable),
        is_empty=False,
    )


class UAParser:
    """UA 解析门面，供 ProfileBuilder / Scorer 注入使用。"""

    __slots__ = ()

    def parse(self, user_agent: str | None) -> UAResult:
        return parse_user_agent(user_agent)

    def parse_to_dict(self, user_agent: str | None) -> dict[str, Any]:
        return parse_user_agent(user_agent).to_dict()

    @staticmethod
    def cache_info() -> Any:
        return parse_user_agent.cache_info()

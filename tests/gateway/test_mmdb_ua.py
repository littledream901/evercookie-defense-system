"""MMDB 读取、UA 解析与规则操作符测试。"""

from __future__ import annotations

import pytest

from fangyu_shared.rules.operators import apply_operator, coerce_asn, read_path
from fangyu_shared.schemas.rule import RuleCondition
from src.infrastructure.mmdb.reader import MMDBReader
from src.infrastructure.ua.crawlers import match_crawler
from src.infrastructure.ua.parser import parse_user_agent

UA_CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
UA_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
)
UA_ANDROID_SAMSUNG = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918B Build/TP1A.220624.014) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
)
UA_IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "Version/16.6 Mobile/15E148 Safari/604.1"
)


class TestUADeviceParsing:
    """设备类型 / 操作系统 / 客户端 / 品牌 四个维度。"""

    def test_desktop_chrome_on_windows(self) -> None:
        r = parse_user_agent(UA_CHROME_WIN)
        assert r.device_type == "desktop"
        assert r.os == "windows"
        assert r.os_version == "10"
        assert r.browser == "chrome"
        assert r.browser_version == "120.0.0.0"
        assert r.engine == "blink"
        assert r.client_type == "browser"
        assert r.is_bot is False
        assert r.is_mobile is False

    def test_mobile_safari_on_iphone(self) -> None:
        r = parse_user_agent(UA_SAFARI_IPHONE)
        assert r.device_type == "mobile"
        assert r.os == "ios"
        assert r.os_version == "17.2"
        assert r.browser == "safari"
        assert r.brand == "apple"
        assert r.model == "iPhone"
        assert r.is_mobile is True

    def test_android_brand_and_model(self) -> None:
        r = parse_user_agent(UA_ANDROID_SAMSUNG)
        assert r.device_type == "mobile"
        assert r.os == "android"
        assert r.os_version == "13"
        assert r.brand == "samsung"
        assert r.model == "SM-S918B"

    def test_tablet_detection(self) -> None:
        r = parse_user_agent(UA_IPAD)
        assert r.device_type == "tablet"
        assert r.brand == "apple"
        assert r.is_mobile is True

    def test_harmonyos_model_skips_noise_tokens(self) -> None:
        ua = (
            "Mozilla/5.0 (Linux; Android 10; HarmonyOS; ELS-AN00; HMSCore) "
            "AppleWebKit/537.36 Chrome/92 HuaweiBrowser/12 Mobile Safari/537.36"
        )
        r = parse_user_agent(ua)
        assert r.os == "harmonyos"
        assert r.brand == "huawei"
        assert r.model == "ELS-AN00"

    def test_in_app_browser_is_app_client_type(self) -> None:
        ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 MicroMessenger/8.0.42(0x18002a2f)"
        )
        r = parse_user_agent(ua)
        assert r.client_type == "app"
        assert r.client_name == "micromessenger"
        assert r.is_bot is False

    def test_empty_ua_flagged(self) -> None:
        for value in ("", "   ", None):
            r = parse_user_agent(value)
            assert r.is_empty is True
            assert r.device_type == "unknown"

    def test_windows_nt_version_mapped(self) -> None:
        r = parse_user_agent("Mozilla/5.0 (Windows NT 6.1; WOW64; rv:11.0) Gecko/20100101 Firefox/115.0")
        assert r.os == "windows"
        assert r.os_version == "7"
        assert r.browser == "firefox"


class TestCrawlerClassification:
    """知名爬虫厂商分类。"""

    @pytest.mark.parametrize(
        ("ua", "category", "vendor"),
        [
            ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "search_engine", "google"),
            ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "search_engine", "bing"),
            ("Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)", "search_engine", "baidu"),
            ("Mozilla/5.0 (compatible; YandexBot/3.0)", "search_engine", "yandex"),
            ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "social", "meta"),
            ("Twitterbot/1.0", "social", "twitter"),
            ("Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)", "ai_crawler", "openai"),
            ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "ai_crawler", "anthropic"),
            ("CCBot/2.0 (https://commoncrawl.org/faq/)", "ai_crawler", "commoncrawl"),
            ("Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", "seo", "ahrefs"),
            ("Mozilla/5.0 (compatible; SemrushBot/7~bl)", "seo", "semrush"),
            ("Pingdom.com_bot_version_1.4", "monitoring", "pingdom"),
            ("Mozilla/5.0 (compatible; UptimeRobot/2.0)", "monitoring", "uptimerobot"),
            ("sqlmap/1.7#stable (https://sqlmap.org)", "security", "sqlmap"),
            ("Mozilla/5.0 Nikto/2.5.0", "security", "nikto"),
            ("Nuclei - Open-source project (github.com/projectdiscovery/nuclei)", "security", "nuclei"),
            ("curl/8.4.0", "library", "curl"),
            ("python-requests/2.31.0", "library", "python-requests"),
            ("Scrapy/2.11.0 (+https://scrapy.org)", "library", "scrapy"),
            ("Go-http-client/2.0", "library", "go-http"),
            ("Feedly/1.0 (+http://www.feedly.com/fetcher.html)", "feed", "feedly"),
            ("ia_archiver (+http://www.alexa.com/site/help/webmasters)", "archive", "internetarchive"),
        ],
    )
    def test_known_vendors(self, ua: str, category: str, vendor: str) -> None:
        r = parse_user_agent(ua)
        assert r.is_bot is True
        assert r.crawler_category == category
        assert r.crawler_vendor == vendor
        assert r.device_type == "bot"

    def test_security_scanner_beats_other_categories(self) -> None:
        """攻击工具伪装成 Googlebot 时，security 分类优先命中。"""
        r = parse_user_agent("Mozilla/5.0 (compatible; Googlebot/2.1) sqlmap/1.7")
        assert r.crawler_category == "security"

    def test_ai_variant_beats_search_engine(self) -> None:
        """Google-Extended 是 AI 语料抓取，不能被 googlebot 规则吞掉。"""
        assert parse_user_agent("Google-Extended").crawler_category == "ai_crawler"
        assert parse_user_agent("Applebot-Extended/1.0").crawler_category == "ai_crawler"

    def test_headless_browser_stays_bot(self) -> None:
        """伪装了完整 Mozilla token 的无头浏览器仍必须判定为 bot。"""
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/120.0.0.0 Safari/537.36"
        r = parse_user_agent(ua)
        assert r.is_bot is True
        assert r.crawler_vendor == "headless-chrome"

    def test_generic_bot_fallback(self) -> None:
        r = parse_user_agent("SomeUnknownCrawler/1.0 (+http://example.com/bot)")
        assert r.is_bot is True
        assert r.crawler_category == "other"
        assert r.crawler_vendor == "unknown"

    def test_real_browser_not_flagged_as_bot(self) -> None:
        for ua in (UA_CHROME_WIN, UA_SAFARI_IPHONE, UA_ANDROID_SAMSUNG, UA_IPAD):
            r = parse_user_agent(ua)
            assert r.is_bot is False, ua
            assert r.crawler_category is None

    def test_match_crawler_returns_none_for_browser(self) -> None:
        assert match_crawler(UA_CHROME_WIN) is None
        assert match_crawler("") is None

    def test_verifiable_flag(self) -> None:
        assert parse_user_agent("Googlebot/2.1").crawler_verifiable is True
        assert parse_user_agent("curl/8.4.0").crawler_verifiable is False


class TestAsnOperators:
    """ASN 精准判定。"""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(4134, 4134), ("4134", 4134), ("AS4134", 4134), ("as4134", 4134), (" AS 4134 ", 4134), (" 4134 ", 4134)],
    )
    def test_coerce_asn_formats(self, value: object, expected: int | None) -> None:
        assert coerce_asn(value) == expected

    def test_coerce_asn_rejects_invalid(self) -> None:
        for value in (None, True, False, "", "ASN4134", "abc", -1, 0, 1.5):
            assert coerce_asn(value) is None

    def test_asn_in_mixed_notation(self) -> None:
        assert apply_operator("asn_in", 4134, [4134, 4837]) is True
        assert apply_operator("asn_in", 4134, ["AS4134"]) is True
        assert apply_operator("asn_in", "AS4134", [4134]) is True
        assert apply_operator("asn_in", 4134, [4837]) is False

    def test_asn_in_requires_sequence(self) -> None:
        assert apply_operator("asn_in", 4134, 4134) is False
        assert apply_operator("asn_in", None, [4134]) is False

    def test_asn_not_in(self) -> None:
        assert apply_operator("asn_not_in", 4134, [4837]) is True
        assert apply_operator("asn_not_in", 4134, [4134]) is False
        assert apply_operator("asn_not_in", 4134, "4134") is False


class TestNetworkOperators:
    """CIDR 名单匹配。"""

    def test_cidr_list_in(self) -> None:
        nets = ["10.0.0.0/8", "203.0.113.0/24"]
        assert apply_operator("cidr_list_in", "10.1.2.3", nets) is True
        assert apply_operator("cidr_list_in", "203.0.113.9", nets) is True
        assert apply_operator("cidr_list_in", "8.8.8.8", nets) is False

    def test_cidr_list_skips_malformed_entries(self) -> None:
        """一条脏数据不应让整个名单失效。"""
        nets = ["not-a-cidr", "", "10.0.0.0/8"]
        assert apply_operator("cidr_list_in", "10.1.2.3", nets) is True

    def test_cidr_list_ipv6(self) -> None:
        assert apply_operator("cidr_list_in", "2001:db8::1", ["2001:db8::/32"]) is True
        assert apply_operator("cidr_list_in", "2001:db8::1", ["10.0.0.0/8"]) is False

    def test_cidr_list_rejects_invalid_ip(self) -> None:
        assert apply_operator("cidr_list_in", "not-an-ip", ["10.0.0.0/8"]) is False
        assert apply_operator("cidr_list_in", None, ["10.0.0.0/8"]) is False

    def test_cidr_list_not_in(self) -> None:
        assert apply_operator("cidr_list_not_in", "8.8.8.8", ["10.0.0.0/8"]) is True
        assert apply_operator("cidr_list_not_in", "10.1.1.1", ["10.0.0.0/8"]) is False


class TestCaseInsensitiveOperators:
    def test_in_ci(self) -> None:
        assert apply_operator("in_ci", "cn", ["CN", "HK"]) is True
        assert apply_operator("in_ci", "CN", ["cn"]) is True
        assert apply_operator("in_ci", " Cn ", ["CN"]) is True
        assert apply_operator("in_ci", "US", ["CN", "HK"]) is False

    def test_not_in_ci(self) -> None:
        assert apply_operator("not_in_ci", "us", ["CN", "HK"]) is True
        assert apply_operator("not_in_ci", "cn", ["CN"]) is False

    def test_unknown_operator_returns_false(self) -> None:
        assert apply_operator("no_such_op", "a", "a") is False


class TestReadPath:
    def test_nested_access(self) -> None:
        ctx = {"ip": {"country": "CN", "asn": 4134}, "ua": {"device_type": "mobile"}}
        assert read_path(ctx, "ip.country") == "CN"
        assert read_path(ctx, "ua.device_type") == "mobile"

    def test_missing_segment_returns_none(self) -> None:
        ctx = {"ip": {"country": "CN"}}
        assert read_path(ctx, "ip.asn") is None
        assert read_path(ctx, "device.fingerprint") is None
        assert read_path(ctx, "ip.country.iso") is None


class TestRuleConditionSchema:
    """新操作符必须能通过 schema 校验，否则规则根本存不进去。"""

    @pytest.mark.parametrize(
        "op",
        ["asn_in", "asn_not_in", "cidr_list_in", "cidr_list_not_in", "in_ci", "not_in_ci"],
    )
    def test_new_operators_accepted(self, op: str) -> None:
        cond = RuleCondition(field="ip.asn", op=op, value=[4134])
        assert cond.op == op

    def test_unknown_operator_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuleCondition(field="ip.asn", op="eval", value=1)


class TestMMDBReader:
    """MMDB 读取器在缺库时必须降级而不是崩溃。"""

    def test_missing_files_degrade_gracefully(self) -> None:
        reader = MMDBReader(country_path="/nonexistent/Country.mmdb", asn_path="/nonexistent/ASN.mmdb")
        result = reader.lookup("8.8.8.8")
        assert result["country"] is None
        assert result["asn"] is None
        assert result["connection_type"] == "unknown"
        assert result["is_proxy"] is False
        assert result["is_datacenter"] is False
        reader.close()

    def test_no_paths_configured(self) -> None:
        reader = MMDBReader()
        result = reader.lookup("1.1.1.1")
        assert result["connection_type"] == "unknown"
        reader.close()

    @pytest.mark.parametrize(
        ("org", "asn", "expected"),
        [
            ("Amazon.com, Inc.", 16509, "datacenter"),
            ("DigitalOcean, LLC", 14061, "datacenter"),
            ("Google LLC", 15169, "datacenter"),
            ("Alibaba (US) Technology Co., Ltd.", 45102, "datacenter"),
            ("China Mobile Communications", 9808, "mobile"),
            ("Vodafone Group", None, "mobile"),
            ("Tsinghua University", None, "education"),
            ("Ministry of Education", None, "education"),
            ("Comcast Cable Communications", None, "residential"),
            ("", None, "unknown"),
        ],
    )
    def test_connection_type_inference(self, org: str, asn: int | None, expected: str) -> None:
        assert MMDBReader._infer_connection_type(org.lower(), asn) == expected

    @pytest.mark.parametrize("org", ["Olympia Networks", "Scompia Holdings"])
    def test_short_keyword_no_false_positive(self, org: str) -> None:
        """pia 是 PIA VPN 的缩写，但不能命中 Olympia/Scompia。"""
        merged = MMDBReader()._merge({}, {"autonomous_system_organization": org, "autonomous_system_number": 1})
        assert merged["is_proxy"] is False
        assert merged["is_vpn"] is False

    def test_vpn_org_detected(self) -> None:
        merged = MMDBReader()._merge(
            {}, {"autonomous_system_organization": "NordVPN Ltd", "autonomous_system_number": 2}
        )
        assert merged["is_proxy"] is True
        assert merged["is_vpn"] is True
        assert merged["asn"] == 2
        assert merged["isp"] == "NordVPN Ltd"

    @pytest.mark.parametrize("org", ["NordVPN Ltd", "ExpressVPN", "Proton VPN", "Mullvad AB"])
    def test_vpn_vendors_recognized(self, org: str) -> None:
        """含 vpn 后缀的品牌名和无 vpn 字样的品牌名都要能识别。"""
        merged = MMDBReader()._merge({}, {"autonomous_system_organization": org})
        assert merged["is_vpn"] is True, org
        assert merged["is_proxy"] is True, org

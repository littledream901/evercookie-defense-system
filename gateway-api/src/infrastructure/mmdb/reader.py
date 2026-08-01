"""MaxMind DB (MMDB) 双文件读取器（Country + ASN）。

设计说明：
- 双文件：GeoLite2-Country.mmdb（地理位置） + GeoLite2-ASN.mmdb（ASN信息）
- 启发式推断：免费版无 is_proxy/is_vpn 标志，通过 ASN org 名称关键词判断
- 网络类型分类：datacenter / mobile / residential / education / government
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import maxminddb

from fangyu_shared.logging import get_logger

_logger = get_logger("gateway.mmdb")

# 已知数据中心/云厂商 ASN（精确匹配，优先级高于关键词）
#
# 为什么需要这张表：组织名关键词匹配会漏掉大量托管商。
# 实测 GeoLite2-ASN 返回的名字是 "Google LLC"、"Alibaba (US) Technology Co., Ltd."、
# "Zenlayer Inc"，都不含 cloud/hosting 字样，只靠关键词会被误判成 residential。
_DATACENTER_ASNS: frozenset[int] = frozenset(
    {
        # Google
        15169, 396982, 19527, 36384, 36385,
        # Amazon AWS
        16509, 14618, 8987, 7224, 38895, 16550, 39111,
        # Microsoft Azure
        8075, 8068, 8069, 8070, 8071, 12076, 58862,
        # Cloudflare
        13335, 209242, 132892, 395747,
        # Akamai / Linode
        20940, 16625, 32787, 63949, 21342,
        # Fastly / CDN77 / DataCamp
        54113, 60068, 212238, 136620,
        # DigitalOcean
        14061, 393406, 200130,
        # Vultr / The Constant Company
        20473, 64515,
        # OVH
        16276, 35540, 54123,
        # Hetzner
        24940, 213230, 212317,
        # Contabo / netcup / IONOS
        51167, 197540, 8560, 34011,
        # Alibaba Cloud
        45102, 37963, 45096, 134963,
        # Tencent Cloud
        45090, 132203, 133478,
        # Huawei Cloud
        55990, 136907, 136908,
        # Baidu Cloud
        38365, 55967,
        # Oracle Cloud
        31898, 7160,
        # IBM / SoftLayer
        36351, 30315,
        # Zenlayer / M247 / Leaseweb / Hostwinds
        21859, 9009, 60781, 16265, 54290,
        # GoDaddy / Namecheap / Unified Layer / Hostgator
        26496, 22612, 46606, 30083,
        # Scaleway / Online SAS
        12876,
        # G-Core / Selectel / Yandex Cloud
        199524, 49505, 208722,
        # Hivelocity / QuadraNet / FranTech / Psychz / Sharktech
        29802, 8100, 53667, 40676, 46844,
        # Choopa / RamNode / BuyVM / Servers.com
        7203, 3223, 50673,
    }
)

# 已知移动/蜂窝网络 ASN
_MOBILE_ASNS: frozenset[int] = frozenset(
    {
        # 中国移动
        9808, 56040, 56041, 56042, 56044, 56046, 56047, 24400, 24547, 9231,
        # 中国联通（移动业务）
        56048, 56049, 56050,
        # 中国电信（移动业务）
        56045, 56051,
        # T-Mobile US / Verizon Wireless / AT&T Mobility
        21928, 22394, 6167, 20057, 6389,
        # Vodafone / Orange / Telefonica
        55410, 3209, 25135, 3215, 12430, 6147,
        # NTT Docomo / SoftBank / KDDI
        9605, 17676, 9824, 2516, 2527,
    }
)

# 已知数据中心/托管商 ASN org 关键词（小写），作为 ASN 表的补充
_DATACENTER_KEYWORDS = {
    "amazon", "aws", "google cloud", "microsoft azure", "azure", "digitalocean",
    "linode", "vultr", "ovh", "hetzner", "contabo", "cloudflare",
    "akamai", "fastly", "alibaba cloud", "tencent cloud", "huawei cloud",
    "oracle cloud", "ibm cloud", "hosting", "datacenter", "data center",
    "cloud", "server", "vps", "colocation", "colo", "dedicated",
    "web services", "internet solutions", "leaseweb", "zenlayer",
}

# 已知 VPN 服务商（不含 "vpn" 字样的品牌名）
_VPN_VENDOR_KEYWORDS = {
    "privateinternetaccess", "mullvad", "tunnelbear", "cyberghost",
    "ipvanish", "surfshark", "windscribe", "hidemyass", "torguard",
}

# is_vpn：匹配 "vpn" 后缀（覆盖 NordVPN/ExpressVPN/ProtonVPN 等）或已知品牌名。
# 用 `vpn\b` 而不是 `\bvpn\b`：后者无法命中 "NordVPN"（d 与 v 之间没有单词边界）。
_VPN_RE = re.compile(
    r"(?:vpn\b|\b(?:" + "|".join(re.escape(kw) for kw in sorted(_VPN_VENDOR_KEYWORDS)) + r")\b)",
    re.IGNORECASE,
)

# is_proxy：代理/匿名化服务。短词按单词边界匹配，避免 "Olympia" 命中 PIA。
_PROXY_RE = re.compile(r"\b(?:proxy|proxies|anonymizer|anonymous|pia|relay|exit node)\b", re.IGNORECASE)

# 已知移动网络运营商关键词
_MOBILE_KEYWORDS = {
    "mobile", "cellular", "wireless", "telecom", "vodafone", "t-mobile",
    "verizon wireless", "att mobility", "sprint", "orange", "telefonica",
    "china mobile", "china unicom", "china telecom", "docomo", "softbank",
}

# 教育/政府网络：\b 边界避免 "gov" 命中 "Govinda"、"edu" 命中 "Eduardo"
_EDUCATION_RE = re.compile(
    r"\b(?:university|universit[eéà]|college|academ(?:y|ia)|school|education|educational|edu|cernet|research and education)\b",
    re.IGNORECASE,
)
_GOVERNMENT_RE = re.compile(
    r"\b(?:government|governmental|gov|ministry|municipal|federal|state of|county of|city of)\b",
    re.IGNORECASE,
)


class MMDBReader:
    """MaxMind 双库读取器：Country + ASN。"""

    def __init__(
        self,
        *,
        country_path: str | Path | None = None,
        asn_path: str | Path | None = None,
    ) -> None:
        self._country_path = Path(country_path) if country_path else None
        self._asn_path = Path(asn_path) if asn_path else None
        self._country_reader: maxminddb.Reader | None = None
        self._asn_reader: maxminddb.Reader | None = None
        self._load()

    def _load(self) -> None:
        if self._country_path and self._country_path.exists():
            try:
                self._country_reader = maxminddb.open_database(str(self._country_path))
                _logger.info("mmdb_country_loaded", path=str(self._country_path))
            except Exception as exc:
                _logger.error("mmdb_country_load_failed", error=str(exc))
                self._country_reader = None
        else:
            _logger.warning("mmdb_country_not_found", path=str(self._country_path))

        if self._asn_path and self._asn_path.exists():
            try:
                self._asn_reader = maxminddb.open_database(str(self._asn_path))
                _logger.info("mmdb_asn_loaded", path=str(self._asn_path))
            except Exception as exc:
                _logger.error("mmdb_asn_load_failed", error=str(exc))
                self._asn_reader = None
        else:
            _logger.warning("mmdb_asn_not_found", path=str(self._asn_path))

    def lookup(self, ip: str) -> dict[str, Any]:
        country_rec = self._lookup_country(ip)
        asn_rec = self._lookup_asn(ip)
        return self._merge(country_rec, asn_rec)

    def _lookup_country(self, ip: str) -> dict[str, Any]:
        if self._country_reader is None:
            return {}
        try:
            return self._country_reader.get(ip) or {}
        except (ValueError, TypeError):
            return {}

    def _lookup_asn(self, ip: str) -> dict[str, Any]:
        if self._asn_reader is None:
            return {}
        try:
            return self._asn_reader.get(ip) or {}
        except (ValueError, TypeError):
            return {}

    def _merge(self, country_rec: dict, asn_rec: dict) -> dict[str, Any]:
        country_data = country_rec.get("country", {})
        continent_data = country_rec.get("continent", {})
        
        asn = asn_rec.get("autonomous_system_number")
        asn_org = asn_rec.get("autonomous_system_organization", "")
        asn_org_lower = asn_org.lower() if asn_org else ""

        connection_type = self._infer_connection_type(asn_org_lower, asn)
        is_vpn = bool(asn_org_lower) and _VPN_RE.search(asn_org_lower) is not None
        # VPN 属于代理的子集，命中 VPN 时 is_proxy 一并置位，
        # 避免运营只配了 ip.isProxy 规则却漏掉 VPN 流量。
        is_proxy = is_vpn or (bool(asn_org_lower) and _PROXY_RE.search(asn_org_lower) is not None)
        is_datacenter = connection_type == "datacenter"
        is_mobile_network = connection_type == "mobile"

        return {
            "continent": continent_data.get("code"),
            "country": country_data.get("iso_code"),
            "asn": asn,
            "asn_org": asn_org or None,
            # isp 与 asn_org 同源：GeoLite2 免费版没有独立的 ISP 库，
            # 保留该字段是为了兼容既有规则和前端展示。
            "isp": asn_org or None,
            "connection_type": connection_type,
            "is_proxy": is_proxy,
            "is_vpn": is_vpn,
            "is_datacenter": is_datacenter,
            "is_mobile_network": is_mobile_network,
        }

    @staticmethod
    def _infer_connection_type(asn_org_lower: str, asn: int | None = None) -> str:
        """推断网络类型。

        判定顺序（先精确后模糊）：
          1. ASN 精确匹配 —— ASN 号稳定且唯一，是最可靠的信号；
          2. 组织名关键词 —— 覆盖表外的长尾托管商；
          3. 兜底 residential。

        GeoLite2 免费版不提供 connection-type 字段，第 2、3 步是启发式推断，
        属于「倾向性信号」而非事实：不应单独作为拦截依据，
        建议与设备指纹、行为特征组合使用。
        """
        if asn is not None:
            if asn in _DATACENTER_ASNS:
                return "datacenter"
            if asn in _MOBILE_ASNS:
                return "mobile"

        if not asn_org_lower:
            return "unknown"
        if any(kw in asn_org_lower for kw in _DATACENTER_KEYWORDS):
            return "datacenter"
        if any(kw in asn_org_lower for kw in _MOBILE_KEYWORDS):
            return "mobile"
        if _EDUCATION_RE.search(asn_org_lower):
            return "education"
        if _GOVERNMENT_RE.search(asn_org_lower):
            return "government"
        return "residential"

    @property
    def available(self) -> bool:
        """两个库是否至少加载了一个。健康检查用。"""
        return self._country_reader is not None or self._asn_reader is not None

    def close(self) -> None:
        if self._country_reader is not None:
            self._country_reader.close()
            self._country_reader = None
        if self._asn_reader is not None:
            self._asn_reader.close()
            self._asn_reader = None

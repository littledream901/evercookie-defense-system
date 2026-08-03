"""已知 ASN 分类常量。

原先硬编码在 ``gateway-api`` 的 MMDB reader 内，现提到 shared：
admin-api 的情报预设与 gateway 的网络类型判定需要共用同一份数据，
否则预设导入的风险分与决策链路的实际认定会漂移。

为什么需要精确 ASN 表：组织名关键词匹配会漏掉大量托管商。实测
GeoLite2-ASN 返回 "Google LLC"、"Alibaba (US) Technology Co., Ltd."、
"Zenlayer Inc"，都不含 cloud/hosting 字样，只靠关键词会误判成 residential。
"""

from __future__ import annotations

DATACENTER_ASNS: frozenset[int] = frozenset(
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
"""数据中心 / 云托管 ASN，精确匹配，优先级高于组织名关键词。"""

MOBILE_ASNS: frozenset[int] = frozenset(
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
"""移动 / 蜂窝网络 ASN。此类 IP 共享度高，风险分应低于数据中心。"""

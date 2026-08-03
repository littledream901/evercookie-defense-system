"""IP 画像的 CIDR 类外部情报源拉取器。

与 :mod:`external_intel_fetcher` 的分工：
- 后者按**单 IP** 拉取「这个 IP 是坏的」（Tor / URLhaus / AbuseIPDB），写
  ``biz_threat_intel``，命中即在 THREAT_INTEL 阶段拦截。
- 本模块按**网段**拉取「这个网段是什么」（数据中心 / VPN），写
  ``biz_intel_ip_profile``，作为画像补全参与风险打分。

只接各家官方公布的地址段清单：格式稳定、无需 API Key、可长期跟随。这填的是
``is_vpn`` / ``network_type`` 目前只能靠 ASN org 名称关键词猜测的缺口——租用云
主机的商业 VPN 用关键词匹配不到。

所有源 fail-open：单源失败不影响其余源。
"""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import httpx
from fangyu_shared.logging import get_logger

_logger = get_logger("admin.cidr_intel_fetcher")

_TIMEOUT = 30
# 单源条目上限，防止上游格式变动导致灌入超预期的数据量
_MAX_PER_SOURCE = 20000

# note 字段的来源前缀，用于统计各源贡献条目数并支持按源回溯
NOTE_PREFIX = "external"


def _normalize_cidr(value: str) -> str | None:
    """规范化网段；非法或裸 IP 之外的格式返回 None。

    上游偶有前后空白或全角字符，统一走 ipaddress 解析后取标准写法。
    """
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError:
        return None


def _record(cidr: str, source_id: str, *, network_type: str, is_vpn: bool, risk_score: int) -> dict[str, Any]:
    return {
        "cidr": cidr,
        "network_type": network_type,
        "is_vpn": is_vpn,
        "is_proxy": is_vpn,
        "is_tor": False,
        "risk_score": risk_score,
        "note": f"{NOTE_PREFIX}:{source_id}",
    }


# 数据中心网段给 45 分，与 ASN 预设里 DATACENTER 的口径保持一致
_DATACENTER_SCORE = 45


class CidrIntelSource:
    """一个 CIDR 源的元信息，供前端卡片展示。"""

    __slots__ = ("description", "id", "name", "url")

    def __init__(self, source_id: str, name: str, url: str, description: str) -> None:
        self.id = source_id
        self.name = name
        self.url = url
        self.description = description

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "enabled": True,
            "requiresApiKey": False,
            "description": self.description,
        }


SOURCES: tuple[CidrIntelSource, ...] = (
    CidrIntelSource(
        "aws",
        "AWS IP Ranges",
        "https://ip-ranges.amazonaws.com/ip-ranges.json",
        "AWS 官方公布的全部服务网段，标记为数据中心",
    ),
    CidrIntelSource(
        "gcp",
        "Google Cloud IP Ranges",
        "https://www.gstatic.com/ipranges/cloud.json",
        "GCP 官方公布的云网段，标记为数据中心",
    ),
    CidrIntelSource(
        "cloudflare",
        "Cloudflare IP Ranges",
        "https://api.cloudflare.com/client/v4/ips",
        "Cloudflare 边缘节点网段，标记为数据中心",
    ),
)

_SOURCE_BY_ID = {s.id: s for s in SOURCES}


class CidrIntelFetcher:
    """从云厂商官方清单拉取网段，产出 ip_profile 记录。"""

    async def fetch_all(self) -> list[dict[str, Any]]:
        """并发拉取所有源，按 cidr 去重后返回。

        先到先得：同一网段被多源覆盖时保留首个，避免同一 cidr 触发唯一键冲突。
        """
        results = await asyncio.gather(
            self._fetch_aws(),
            self._fetch_gcp(),
            self._fetch_cloudflare(),
            return_exceptions=True,
        )
        merged: dict[str, dict[str, Any]] = {}
        for r in results:
            if isinstance(r, BaseException):
                _logger.warning("cidr_intel_source_failed", error=str(r))
                continue
            for rec in r:
                merged.setdefault(rec["cidr"], rec)
        return list(merged.values())

    async def _get_json(self, source_id: str) -> Any | None:
        url = _SOURCE_BY_ID[source_id].url
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            _logger.warning("cidr_fetch_failed", source=source_id, error=str(exc))
            return None

    async def _fetch_aws(self) -> list[dict[str, Any]]:
        """AWS：prefixes[].ip_prefix 与 ipv6_prefixes[].ipv6_prefix。"""
        data = await self._get_json("aws")
        if not isinstance(data, dict):
            return []
        raw: list[str] = []
        for key, field in (("prefixes", "ip_prefix"), ("ipv6_prefixes", "ipv6_prefix")):
            for item in data.get(key) or ():
                if isinstance(item, dict) and item.get(field):
                    raw.append(str(item[field]))
        return self._to_records(raw, "aws")

    async def _fetch_gcp(self) -> list[dict[str, Any]]:
        """GCP：prefixes[].ipv4Prefix / ipv6Prefix。"""
        data = await self._get_json("gcp")
        if not isinstance(data, dict):
            return []
        raw: list[str] = []
        for item in data.get("prefixes") or ():
            if not isinstance(item, dict):
                continue
            value = item.get("ipv4Prefix") or item.get("ipv6Prefix")
            if value:
                raw.append(str(value))
        return self._to_records(raw, "gcp")

    async def _fetch_cloudflare(self) -> list[dict[str, Any]]:
        """Cloudflare：result.ipv4_cidrs / ipv6_cidrs。"""
        data = await self._get_json("cloudflare")
        if not isinstance(data, dict):
            return []
        result = data.get("result")
        if not isinstance(result, dict):
            return []
        raw: list[str] = []
        for key in ("ipv4_cidrs", "ipv6_cidrs"):
            for value in result.get(key) or ():
                raw.append(str(value))
        return self._to_records(raw, "cloudflare")

    def _to_records(self, raw: list[str], source_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for value in raw:
            cidr = _normalize_cidr(value)
            if cidr is None:
                continue
            out.append(
                _record(
                    cidr,
                    source_id,
                    network_type="DATACENTER",
                    is_vpn=False,
                    risk_score=_DATACENTER_SCORE,
                )
            )
            if len(out) >= _MAX_PER_SOURCE:
                _logger.warning("cidr_source_truncated", source=source_id, limit=_MAX_PER_SOURCE)
                break
        return out

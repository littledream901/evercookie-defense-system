"""外部威胁情报源拉取器。

支持的源（均为免费或公开协议）：
- Tor Exit Nodes：https://check.torproject.org/torbulkexitlist
- URLhaus 最近活跃恶意 URL 的 Host IP（abuse.ch 开放数据）
- AbuseIPDB：需要 API Key，可通过环境变量 ABUSEIPDB_API_KEY 配置

所有源均 fail-open：单个源失败不影响其他源，最终返回合并结果。
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
from typing import Any

import httpx
from fangyu_shared.logging import get_logger

_logger = get_logger("admin.external_intel_fetcher")

# 单次 HTTP 请求超时（秒）
_TIMEOUT = 20


def _normalize_ip(ip_str: str) -> str | None:
    """规范化 IP，返回压缩表示；格式非法时返回 None。"""
    try:
        return str(ipaddress.ip_address(ip_str.strip()))
    except ValueError:
        return None


class ExternalIntelFetcher:
    """从多个公开威胁情报源异步拉取 IP 列表。"""

    async def fetch_all(self) -> list[dict[str, Any]]:
        """并发拉取所有源，合并去重后返回。"""
        results = await asyncio.gather(
            self._fetch_tor_exit_nodes(),
            self._fetch_urlhaus(),
            self._fetch_abuseipdb(),
            return_exceptions=True,
        )
        merged: dict[str, dict[str, Any]] = {}
        for r in results:
            if isinstance(r, Exception):
                _logger.warning("external_intel_source_failed", error=str(r))
                continue
            for entry in r:
                ip = entry["ip"]
                if ip not in merged:
                    merged[ip] = entry
        return list(merged.values())

    async def _fetch_tor_exit_nodes(self) -> list[dict[str, Any]]:
        """拉取 Tor 出口节点列表（每行一个 IP）。"""
        url = "https://check.torproject.org/torbulkexitlist"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception as exc:
            _logger.warning("tor_fetch_failed", error=str(exc))
            return []

        entries = []
        for line in resp.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ip = _normalize_ip(line)
            if ip:
                entries.append({
                    "ip": ip,
                    "category": "tor",
                    "severity": "high",
                    "source": "tor_project",
                    "confidence": 95,
                    "description": "Tor exit node",
                })
        _logger.info("tor_fetch_done", count=len(entries))
        return entries

    async def _fetch_urlhaus(self) -> list[dict[str, Any]]:
        """从 URLhaus 拉取最近活跃恶意 URL 的 Host。

        使用 CSV 格式，取 URL 中解析到 IP 的条目（Host 字段直接是 IP 的情况）。
        免费开放，无需 API Key：https://urlhaus.abuse.ch/downloads/csv_recent/
        """
        url = "https://urlhaus.abuse.ch/downloads/csv_recent/"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception as exc:
            _logger.warning("urlhaus_fetch_failed", error=str(exc))
            return []

        entries = []
        for line in resp.text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            # CSV 格式：id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter
            parts = line.split('","')
            if len(parts) < 3:
                continue
            raw_url = parts[2].strip('"')
            # 从 URL 提取 Host
            try:
                from urllib.parse import urlparse
                host = urlparse(raw_url).hostname or ""
                ip = _normalize_ip(host)
                if ip:
                    threat = parts[5].strip('"') if len(parts) > 5 else "malware"
                    entries.append({
                        "ip": ip,
                        "category": "malicious",
                        "severity": "high",
                        "source": "urlhaus",
                        "confidence": 85,
                        "description": f"URLhaus: {threat}",
                    })
            except Exception:
                continue

        # 去重
        seen: set[str] = set()
        unique = []
        for e in entries:
            if e["ip"] not in seen:
                seen.add(e["ip"])
                unique.append(e)

        _logger.info("urlhaus_fetch_done", count=len(unique))
        return unique

    async def _fetch_abuseipdb(self) -> list[dict[str, Any]]:
        """从 AbuseIPDB 拉取黑名单 Top-1000。

        需要环境变量 ABUSEIPDB_API_KEY。
        无 Key 时静默跳过，不影响其他源。
        文档：https://docs.abuseipdb.com/#blacklist-endpoint
        """
        api_key = os.getenv("ABUSEIPDB_API_KEY", "")
        if not api_key:
            return []

        url = "https://api.abuseipdb.com/api/v2/blacklist"
        headers = {"Key": api_key, "Accept": "application/json"}
        params = {"confidenceMinimum": "75", "limit": "1000"}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            _logger.warning("abuseipdb_fetch_failed", error=str(exc))
            return []

        entries = []
        for item in data.get("data", []):
            ip = _normalize_ip(str(item.get("ipAddress", "")))
            if not ip:
                continue
            confidence = int(item.get("abuseConfidenceScore", 75))
            entries.append({
                "ip": ip,
                "category": "malicious",
                "severity": "high" if confidence >= 90 else "medium",
                "source": "abuseipdb",
                "confidence": min(confidence, 100),
                "description": f"AbuseIPDB score={confidence}",
            })
        _logger.info("abuseipdb_fetch_done", count=len(entries))
        return entries

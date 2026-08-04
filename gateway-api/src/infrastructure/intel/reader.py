"""从 Redis 读取后台维护的五类维度情报。

数据由 admin-api 的 ``IntelSync`` 全量写入，结构为 Hash（field = 主键）：
  fangyu:intel:asn           asn        → {network_type, country, risk_score, operator}
  fangyu:intel:crawler       pattern    → {crawler_category, crawler_name, ...}
  fangyu:intel:fingerprint   finger_id  → {finger_type, risk_score}
  fangyu:intel:geo_ip        cidr       → {country, region, city}
  fangyu:intel:ip_profile    cidr       → {network_type, is_vpn, is_proxy, ...}

asn / fingerprint 类可直接 HGET；CIDR 类必须 HGETALL 后在内存做网段匹配，故带
进程内缓存（TTL 30s），避免每请求全量拉取，且编译成按前缀长度分层的哈希索引
（:class:`_CidrIndex`）而非线性表，使匹配开销不随条目数增长。crawler 类需正则
匹配，同样缓存并预编译。

情报是 MMDB 的**覆盖层**而非替代：仅当后台确实录了条目时才覆盖对应字段。
任何 Redis 故障都不该让决策请求变成 500，故全异常兜底为「无命中」。
"""

from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass, field
from typing import Any

import orjson
from fangyu_shared.intel.keys import (
    ASN_KEY,
    CRAWLER_KEY,
    FINGERPRINT_KEY,
    GEO_IP_KEY,
    IP_PROFILE_KEY,
)
from fangyu_shared.logging import get_logger
from redis.asyncio import Redis

_logger = get_logger("gateway.intel_reader")

_LOCAL_TTL_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class IntelHit:
    """一次请求的情报命中汇总。

    ``ip_overrides``
        直接覆盖到 :class:`IpProfile` 的字段（Python 字段名，非 alias）。
    ``risk_score``
        各维度 risk_score 取最大值，由 ``IntelScorer`` 消费。
    ``reasons``
        命中来源，用于排障与事件落库。
    """

    ip_overrides: dict[str, Any] = field(default_factory=dict)
    risk_score: int = 0
    reasons: tuple[str, ...] = ()
    crawler_category: str | None = None
    crawler_name: str | None = None
    is_legitimate_crawler: bool = False

    @property
    def matched(self) -> bool:
        return bool(self.reasons)


_MISS = IntelHit()


@dataclass(slots=True)
class _CidrEntry:
    network: ipaddress.IPv4Network | ipaddress.IPv6Network
    payload: dict[str, Any]


_ADDR_BITS = {4: 32, 6: 128}


@dataclass(slots=True)
class _CidrIndex:
    """按前缀长度分层的网段索引，支持最长前缀优先匹配。

    ``levels[version]`` 是 ``(prefixlen, {网络号 → 条目})`` 的列表，按 prefixlen
    降序。查询时对每个存在的前缀长度做一次哈希查找，命中即返回，因此耗时只与
    「不同前缀长度的种数」相关（IPv4 最多 33 种），与条目总数无关。这让情报可以
    承载数万条 CIDR 而不拖慢决策热路径。
    """

    levels: dict[int, list[tuple[int, dict[int, _CidrEntry]]]]

    def match(self, addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> _CidrEntry | None:
        bits = _ADDR_BITS[addr.version]
        addr_int = int(addr)
        for prefixlen, bucket in self.levels.get(addr.version, ()):
            hit = bucket.get(addr_int >> (bits - prefixlen))
            if hit is not None:
                return hit
        return None


def _build_cidr_index(raw: dict[str, str]) -> _CidrIndex:
    """把 Redis Hash（field = CIDR）编译成 :class:`_CidrIndex`。

    非法 CIDR 或非法 JSON 的条目直接跳过：情报由后台录入，单条脏数据不应让
    整个维度失效。
    """
    buckets: dict[int, dict[int, dict[int, _CidrEntry]]] = {4: {}, 6: {}}
    for cidr, payload in raw.items():
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            data = orjson.loads(payload)
        except (ValueError, orjson.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        bits = _ADDR_BITS[network.version]
        key = int(network.network_address) >> (bits - network.prefixlen)
        per_len = buckets[network.version].setdefault(network.prefixlen, {})
        per_len.setdefault(key, _CidrEntry(network=network, payload=data))

    return _CidrIndex(
        levels={
            version: sorted(per_version.items(), key=lambda item: item[0], reverse=True)
            for version, per_version in buckets.items()
        }
    )


@dataclass(slots=True)
class _PatternEntry:
    regex: re.Pattern[str]
    payload: dict[str, Any]


@dataclass(slots=True)
class _Cached:
    value: Any
    expires_at: float


class IntelReader:
    """六类维度情报的统一读取入口。"""

    def __init__(self, redis: Redis, *, local_ttl_seconds: float = _LOCAL_TTL_SECONDS) -> None:
        self._redis = redis
        self._local_ttl = local_ttl_seconds
        self._cache: dict[str, _Cached] = {}

    # ── 本地缓存 ──────────────────────────────────────────────────────────────

    async def _hgetall_cached(self, key: str) -> dict[str, str]:
        now = time.monotonic()
        entry = self._cache.get(key)
        if entry is not None and entry.expires_at > now:
            return entry.value
        try:
            raw = await self._redis.hgetall(key)  # type: ignore[misc]
        except Exception as exc:
            _logger.warning("intel_hgetall_failed", key=key, error=str(exc))
            raw = {}
        self._cache[key] = _Cached(value=raw, expires_at=now + self._local_ttl)
        return raw

    async def _cidr_index(self, key: str) -> _CidrIndex:
        cache_key = f"{key}:parsed"
        now = time.monotonic()
        entry = self._cache.get(cache_key)
        if entry is not None and entry.expires_at > now:
            return entry.value

        index = _build_cidr_index(await self._hgetall_cached(key))
        self._cache[cache_key] = _Cached(value=index, expires_at=now + self._local_ttl)
        return index

    async def _pattern_entries(self) -> list[_PatternEntry]:
        cache_key = f"{CRAWLER_KEY}:parsed"
        now = time.monotonic()
        entry = self._cache.get(cache_key)
        if entry is not None and entry.expires_at > now:
            return entry.value

        raw = await self._hgetall_cached(CRAWLER_KEY)
        entries: list[_PatternEntry] = []
        for pattern, payload in raw.items():
            try:
                regex = re.compile(pattern, re.IGNORECASE)
                data = orjson.loads(payload)
            except (re.error, orjson.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict):
                entries.append(_PatternEntry(regex=regex, payload=data))
        self._cache[cache_key] = _Cached(value=entries, expires_at=now + self._local_ttl)
        return entries

    async def _hget(self, key: str, field_name: str) -> dict[str, Any] | None:
        try:
            raw = await self._redis.hget(key, field_name)  # type: ignore[misc]
        except Exception as exc:
            _logger.warning("intel_hget_failed", key=key, error=str(exc))
            return None
        if not raw:
            return None
        try:
            data = orjson.loads(raw)
        except (orjson.JSONDecodeError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def lookup(
        self,
        *,
        ip: str,
        asn: int | None,
        fingerprint: str,
        user_agent: str,
    ) -> IntelHit:
        """汇总六类情报。任何一类失败都不影响其余类别。"""
        overrides: dict[str, Any] = {}
        reasons: list[str] = []
        scores: list[int] = []
        crawler_category: str | None = None
        crawler_name: str | None = None
        is_legit = False

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            addr = None

        # geo_ip：覆盖 MMDB 的地理归属
        if addr is not None:
            geo = (await self._cidr_index(GEO_IP_KEY)).match(addr)
            if geo is not None:
                for f in ("country", "region", "city"):
                    v = geo.payload.get(f)
                    if v:
                        overrides[f] = v
                reasons.append(f"intel:geo_ip:{geo.network}")

        # ip_profile：覆盖代理 / VPN / Tor / 网络类型
        if addr is not None:
            profile_hit = (await self._cidr_index(IP_PROFILE_KEY)).match(addr)
            if profile_hit is not None:
                overrides.update(_network_flags(profile_hit.payload))
                score = _as_int(profile_hit.payload.get("risk_score"))
                if score:
                    scores.append(score)
                reasons.append(f"intel:ip_profile:{profile_hit.network}")

        # asn：补全运营商 / 国别 + 风险标注
        if asn is not None:
            asn_intel = await self._hget(ASN_KEY, str(asn))
            if asn_intel:
                if asn_intel.get("operator"):
                    overrides["asn_org"] = asn_intel["operator"]
                # geo_ip 的国别优先级更高，已写入则不覆盖
                if asn_intel.get("country") and "country" not in overrides:
                    overrides["country"] = asn_intel["country"]
                overrides.update(_network_flags(asn_intel))
                score = _as_int(asn_intel.get("risk_score"))
                if score:
                    scores.append(score)
                reasons.append(f"intel:asn:{asn}")

        # fingerprint：已知自动化工具指纹
        if fingerprint:
            fp = await self._hget(FINGERPRINT_KEY, fingerprint)
            if fp:
                score = _as_int(fp.get("risk_score"))
                if score:
                    scores.append(score)
                reasons.append(f"intel:fingerprint:{fp.get('finger_type', 'device')}")

        # crawler：UA 特征串匹配
        if user_agent:
            for entry in await self._pattern_entries():
                if entry.regex.search(user_agent):
                    crawler_category = entry.payload.get("crawler_category") or None
                    crawler_name = entry.payload.get("crawler_name") or None
                    is_legit = bool(entry.payload.get("is_legitimate"))
                    if not is_legit:
                        score = _as_int(entry.payload.get("risk_score"))
                        if score:
                            scores.append(score)
                    reasons.append(f"intel:crawler:{crawler_name or crawler_category}")
                    break

        if not reasons:
            return _MISS

        return IntelHit(
            ip_overrides=overrides,
            risk_score=max(scores) if scores else 0,
            reasons=tuple(reasons),
            crawler_category=crawler_category,
            crawler_name=crawler_name,
            is_legitimate_crawler=is_legit,
        )


def _network_flags(payload: dict[str, Any]) -> dict[str, Any]:
    """把情报里的 network_type / 代理标志翻译成 IpProfile 字段。

    后台存的是大写枚举（DATACENTER），gateway 侧统一小写。
    """
    out: dict[str, Any] = {}
    raw_type = payload.get("network_type")
    if raw_type:
        conn = str(raw_type).lower()
        out["connection_type"] = conn
        out["is_datacenter"] = conn == "datacenter"
        out["is_mobile_network"] = conn == "mobile"
    for f in ("is_vpn", "is_proxy", "is_tor"):
        if payload.get(f):
            out[f] = True
    # VPN 是代理的子集，与 MMDBReader 的语义保持一致
    if out.get("is_vpn") or out.get("is_tor"):
        out["is_proxy"] = True
    return out


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

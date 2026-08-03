"""CIDR 情报前缀索引测试。

覆盖最长前缀优先、IPv4/IPv6 隔离、脏数据跳过，以及 IntelReader 端到端命中。
索引替换了原先的线性扫描，这些断言保证语义不变。
"""

from __future__ import annotations

import ipaddress

import orjson
import pytest
from fangyu_shared.intel.keys import IP_PROFILE_KEY
from src.infrastructure.intel.reader import IntelReader, _build_cidr_index


def _raw(mapping: dict[str, dict]) -> dict[str, str]:
    return {k: orjson.dumps(v).decode() for k, v in mapping.items()}


class _FakeRedis:
    """只实现 IntelReader 用到的 hgetall / hget。"""

    def __init__(self, hashes: dict[str, dict[str, str]]) -> None:
        self._hashes = hashes

    async def hgetall(self, key: str) -> dict[str, str]:
        return self._hashes.get(key, {})

    async def hget(self, key: str, field: str) -> str | None:
        return self._hashes.get(key, {}).get(field)


class TestBuildCidrIndex:
    def test_longest_prefix_wins(self) -> None:
        index = _build_cidr_index(
            _raw(
                {
                    "10.0.0.0/8": {"tag": "wide"},
                    "10.1.0.0/16": {"tag": "mid"},
                    "10.1.2.0/24": {"tag": "narrow"},
                }
            )
        )
        hit = index.match(ipaddress.ip_address("10.1.2.3"))
        assert hit is not None
        assert hit.payload["tag"] == "narrow"

        hit = index.match(ipaddress.ip_address("10.1.9.9"))
        assert hit is not None
        assert hit.payload["tag"] == "mid"

        hit = index.match(ipaddress.ip_address("10.9.9.9"))
        assert hit is not None
        assert hit.payload["tag"] == "wide"

    def test_miss_returns_none(self) -> None:
        index = _build_cidr_index(_raw({"10.0.0.0/8": {"tag": "x"}}))
        assert index.match(ipaddress.ip_address("11.0.0.1")) is None

    def test_single_host_prefix(self) -> None:
        index = _build_cidr_index(_raw({"203.0.113.7/32": {"tag": "host"}}))
        assert index.match(ipaddress.ip_address("203.0.113.7")) is not None
        assert index.match(ipaddress.ip_address("203.0.113.8")) is None

    def test_default_route_matches_everything(self) -> None:
        index = _build_cidr_index(_raw({"0.0.0.0/0": {"tag": "any"}}))
        hit = index.match(ipaddress.ip_address("8.8.8.8"))
        assert hit is not None
        assert hit.payload["tag"] == "any"

    def test_ipv4_and_ipv6_do_not_cross_match(self) -> None:
        index = _build_cidr_index(
            _raw({"10.0.0.0/8": {"tag": "v4"}, "2001:db8::/32": {"tag": "v6"}})
        )
        v4 = index.match(ipaddress.ip_address("10.0.0.1"))
        v6 = index.match(ipaddress.ip_address("2001:db8::1"))
        assert v4 is not None and v4.payload["tag"] == "v4"
        assert v6 is not None and v6.payload["tag"] == "v6"
        assert index.match(ipaddress.ip_address("2001:dead::1")) is None

    def test_ipv6_longest_prefix(self) -> None:
        index = _build_cidr_index(
            _raw({"2001:db8::/32": {"tag": "wide"}, "2001:db8:1::/48": {"tag": "narrow"}})
        )
        hit = index.match(ipaddress.ip_address("2001:db8:1::5"))
        assert hit is not None
        assert hit.payload["tag"] == "narrow"

    def test_bare_ip_treated_as_host_route(self) -> None:
        """后台可能只录了单个 IP，不带掩码。"""
        index = _build_cidr_index(_raw({"198.51.100.4": {"tag": "bare"}}))
        assert index.match(ipaddress.ip_address("198.51.100.4")) is not None

    def test_non_strict_cidr_is_normalised(self) -> None:
        """10.1.2.3/24 这类主机位非零的写法按 strict=False 归一到网段。"""
        index = _build_cidr_index(_raw({"10.1.2.3/24": {"tag": "loose"}}))
        hit = index.match(ipaddress.ip_address("10.1.2.99"))
        assert hit is not None
        assert str(hit.network) == "10.1.2.0/24"

    @pytest.mark.parametrize("bad_key", ["not-an-ip", "10.0.0.0/99", ""])
    def test_invalid_cidr_skipped(self, bad_key: str) -> None:
        index = _build_cidr_index(
            {**_raw({bad_key: {"tag": "bad"}}), **_raw({"10.0.0.0/8": {"tag": "ok"}})}
        )
        hit = index.match(ipaddress.ip_address("10.0.0.1"))
        assert hit is not None
        assert hit.payload["tag"] == "ok"

    def test_invalid_json_skipped(self) -> None:
        index = _build_cidr_index({"10.0.0.0/8": "{not json", "10.1.0.0/16": '{"tag":"ok"}'})
        assert index.match(ipaddress.ip_address("10.9.9.9")) is None
        assert index.match(ipaddress.ip_address("10.1.0.1")) is not None

    def test_non_dict_payload_skipped(self) -> None:
        index = _build_cidr_index({"10.0.0.0/8": "[1,2,3]"})
        assert index.match(ipaddress.ip_address("10.0.0.1")) is None

    def test_empty_hash(self) -> None:
        index = _build_cidr_index({})
        assert index.match(ipaddress.ip_address("10.0.0.1")) is None


class TestIntelReaderCidrLookup:
    @pytest.mark.asyncio
    async def test_ip_profile_hit_applies_flags_and_score(self) -> None:
        redis = _FakeRedis(
            {
                IP_PROFILE_KEY: _raw(
                    {
                        "192.0.2.0/24": {"network_type": "DATACENTER", "risk_score": 45},
                        "192.0.2.128/25": {"is_tor": True, "risk_score": 80},
                    }
                )
            }
        )
        reader = IntelReader(redis)  # type: ignore[arg-type]

        hit = await reader.lookup(ip="192.0.2.200", asn=None, fingerprint="", user_agent="")
        assert hit.matched
        assert hit.ip_overrides.get("is_tor") is True
        assert hit.risk_score == 80
        assert "intel:ip_profile:192.0.2.128/25" in hit.reasons

        reader2 = IntelReader(redis)  # type: ignore[arg-type]
        hit2 = await reader2.lookup(ip="192.0.2.10", asn=None, fingerprint="", user_agent="")
        assert hit2.ip_overrides.get("connection_type") == "datacenter"
        assert hit2.risk_score == 45

    @pytest.mark.asyncio
    async def test_no_hit_returns_miss(self) -> None:
        redis = _FakeRedis({IP_PROFILE_KEY: _raw({"192.0.2.0/24": {"risk_score": 10}})})
        reader = IntelReader(redis)  # type: ignore[arg-type]
        hit = await reader.lookup(ip="203.0.113.1", asn=None, fingerprint="", user_agent="")
        assert not hit.matched

    @pytest.mark.asyncio
    async def test_invalid_ip_skips_cidr_dimensions(self) -> None:
        redis = _FakeRedis({IP_PROFILE_KEY: _raw({"0.0.0.0/0": {"risk_score": 99}})})
        reader = IntelReader(redis)  # type: ignore[arg-type]
        hit = await reader.lookup(ip="not-an-ip", asn=None, fingerprint="", user_agent="")
        assert not hit.matched

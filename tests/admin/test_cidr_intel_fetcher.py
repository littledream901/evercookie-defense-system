"""IP 画像 CIDR 外部源拉取器测试。

不发真实网络请求：直接替换各源的 JSON 获取，只校验解析、归一与 fail-open。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from src.infrastructure.cidr_intel_fetcher import (
    NOTE_PREFIX,
    SOURCES,
    CidrIntelFetcher,
    _normalize_cidr,
)

_AWS_PAYLOAD = {
    "prefixes": [{"ip_prefix": "13.34.0.0/24"}, {"ip_prefix": " 13.35.0.0/24 "}],
    "ipv6_prefixes": [{"ipv6_prefix": "2600:1f00::/40"}],
}
_GCP_PAYLOAD = {
    "prefixes": [
        {"ipv4Prefix": "34.1.0.0/16"},
        {"ipv6Prefix": "2600:1900::/28"},
        {"service": "no-prefix-here"},
    ]
}
_CF_PAYLOAD = {"result": {"ipv4_cidrs": ["173.245.48.0/20"], "ipv6_cidrs": ["2400:cb00::/32"]}}


def _fake_get_json(payloads: dict[str, Any]):
    async def _inner(self: CidrIntelFetcher, source_id: str) -> Any:
        return payloads.get(source_id)

    return _inner


class TestNormalizeCidr:
    def test_strips_whitespace(self) -> None:
        assert _normalize_cidr("  10.0.0.0/8 ") == "10.0.0.0/8"

    def test_bare_ip_becomes_host_route(self) -> None:
        assert _normalize_cidr("1.2.3.4") == "1.2.3.4/32"

    def test_host_bits_normalised(self) -> None:
        assert _normalize_cidr("10.1.2.3/24") == "10.1.2.0/24"

    @pytest.mark.parametrize("bad", ["", "nonsense", "10.0.0.0/99", "1.2.3.4.5"])
    def test_invalid_returns_none(self, bad: str) -> None:
        assert _normalize_cidr(bad) is None


class TestSourceMetadata:
    def test_all_sources_expose_card_fields(self) -> None:
        for s in SOURCES:
            d = s.as_dict()
            assert d["id"] and d["name"] and d["url"]
            assert d["enabled"] is True
            assert d["requiresApiKey"] is False

    def test_source_ids_unique(self) -> None:
        ids = [s.id for s in SOURCES]
        assert len(ids) == len(set(ids))


class TestFetchAll:
    @pytest.mark.asyncio
    async def test_parses_all_three_sources(self) -> None:
        payloads = {"aws": _AWS_PAYLOAD, "gcp": _GCP_PAYLOAD, "cloudflare": _CF_PAYLOAD}
        with patch.object(CidrIntelFetcher, "_get_json", _fake_get_json(payloads)):
            records = await CidrIntelFetcher().fetch_all()

        cidrs = {r["cidr"] for r in records}
        assert "13.34.0.0/24" in cidrs
        assert "13.35.0.0/24" in cidrs  # 前后空白被清理
        assert "2600:1f00::/40" in cidrs
        assert "34.1.0.0/16" in cidrs
        assert "173.245.48.0/20" in cidrs
        assert "2400:cb00::/32" in cidrs
        assert len(records) == 7

    @pytest.mark.asyncio
    async def test_records_shape_matches_ip_profile_columns(self) -> None:
        with patch.object(CidrIntelFetcher, "_get_json", _fake_get_json({"aws": _AWS_PAYLOAD})):
            records = await CidrIntelFetcher().fetch_all()

        rec = records[0]
        assert set(rec) == {
            "cidr",
            "network_type",
            "is_vpn",
            "is_proxy",
            "is_tor",
            "risk_score",
            "note",
        }
        assert rec["network_type"] == "DATACENTER"
        assert rec["is_tor"] is False
        assert rec["risk_score"] == 45
        assert rec["note"] == f"{NOTE_PREFIX}:aws"

    @pytest.mark.asyncio
    async def test_single_source_failure_does_not_break_others(self) -> None:
        """aws 返回 None（模拟 HTTP 失败），仍应拿到其余两源。"""
        payloads = {"aws": None, "gcp": _GCP_PAYLOAD, "cloudflare": _CF_PAYLOAD}
        with patch.object(CidrIntelFetcher, "_get_json", _fake_get_json(payloads)):
            records = await CidrIntelFetcher().fetch_all()

        assert records
        assert all(not r["note"].endswith(":aws") for r in records)

    @pytest.mark.asyncio
    async def test_all_sources_failing_returns_empty(self) -> None:
        with patch.object(CidrIntelFetcher, "_get_json", _fake_get_json({})):
            assert await CidrIntelFetcher().fetch_all() == []

    @pytest.mark.asyncio
    async def test_unexpected_upstream_shape_is_tolerated(self) -> None:
        """上游改版成列表 / 缺 result 时不应抛异常。"""
        payloads = {"aws": ["unexpected"], "gcp": {"prefixes": None}, "cloudflare": {"ok": True}}
        with patch.object(CidrIntelFetcher, "_get_json", _fake_get_json(payloads)):
            assert await CidrIntelFetcher().fetch_all() == []

    @pytest.mark.asyncio
    async def test_duplicate_cidr_across_sources_deduped(self) -> None:
        dup = {"prefixes": [{"ipv4Prefix": "13.34.0.0/24"}]}
        payloads = {"aws": _AWS_PAYLOAD, "gcp": dup}
        with patch.object(CidrIntelFetcher, "_get_json", _fake_get_json(payloads)):
            records = await CidrIntelFetcher().fetch_all()

        assert [r["cidr"] for r in records].count("13.34.0.0/24") == 1

    @pytest.mark.asyncio
    async def test_exception_from_source_is_swallowed(self) -> None:
        async def _boom(self: CidrIntelFetcher, source_id: str) -> Any:
            if source_id == "aws":
                raise RuntimeError("boom")
            return _CF_PAYLOAD if source_id == "cloudflare" else None

        with patch.object(CidrIntelFetcher, "_get_json", _boom):
            records = await CidrIntelFetcher().fetch_all()

        assert {r["cidr"] for r in records} == {"173.245.48.0/20", "2400:cb00::/32"}


class TestGetJsonErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_returns_none(self) -> None:
        with patch("httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(side_effect=RuntimeError("network down"))
            assert await CidrIntelFetcher()._get_json("aws") is None

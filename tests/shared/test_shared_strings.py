"""fangyu_shared.utils.strings 单元测试。"""
from __future__ import annotations

import pytest

from fangyu_shared.utils.strings import mask_email, mask_ip, truncate


class TestTruncate:
    def test_none_returns_empty(self):
        assert truncate(None) == ""

    def test_short_string_unchanged(self):
        assert truncate("abc", max_length=5) == "abc"

    def test_long_string_truncated(self):
        assert truncate("abcdefghij", max_length=6) == "abc..."

    def test_custom_suffix(self):
        assert truncate("abcdefghij", max_length=6, suffix="~~") == "abcd~~"


class TestMaskEmail:
    def test_empty_returns_empty(self):
        assert mask_email(None) == ""
        assert mask_email("") == ""
        assert mask_email("no-at-sign") == ""

    def test_short_local_masked_fully(self):
        assert mask_email("ab@example.com") == "**@example.com"

    def test_long_local_keeps_first_and_last(self):
        assert mask_email("john@example.com") == "j**n@example.com"


class TestMaskIp:
    def test_empty_returns_empty(self):
        assert mask_ip(None) == ""
        assert mask_ip("") == ""

    def test_invalid_returns_stars(self):
        assert mask_ip("not-an-ip") == "***"

    def test_ipv4_keeps_first_two_segments(self):
        assert mask_ip("192.168.1.100") == "192.168.*.*"

    @pytest.mark.parametrize("ip", ["10.0.0.1", "172.16.31.200"])
    def test_ipv4_various(self, ip: str):
        parts = ip.split(".")
        assert mask_ip(ip) == f"{parts[0]}.{parts[1]}.*.*"

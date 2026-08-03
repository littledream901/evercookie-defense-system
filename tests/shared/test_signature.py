"""签名契约测试。

这些断言锁的是**跨语言一致性**：gateway（Python）、client-sdk（TS）、
WordPress（PHP）、nginx-lua（Lua）必须对同一参数集算出同一签名。任何一条
改动都会让已部署的适配器验签失败，因此这里逐条钉死编码行为。
"""

from __future__ import annotations

import pytest
from fangyu_shared.utils.crypto import (
    build_sign_payload,
    generate_nonce,
    is_timestamp_fresh,
    sign_params,
    verify_params_signature,
)

SECRET = "s3cr3t-app-key"


# ── 待签串构造 ──


def test_keys_are_sorted_lexicographically():
    payload = build_sign_payload({"b": "2", "a": "1", "c": "3"})
    assert payload == "a=1&b=2&c=3"


def test_sign_field_is_excluded():
    payload = build_sign_payload({"a": "1", "sign": "deadbeef"})
    assert payload == "a=1"


def test_none_and_empty_values_are_dropped():
    """缺失与空串必须等价，否则不同接入方算出的签名会不一致。"""
    assert build_sign_payload({"a": "1", "b": None, "c": ""}) == "a=1"
    assert build_sign_payload({"a": "1"}) == build_sign_payload({"a": "1", "b": None})


def test_bool_is_lowercased():
    """Python str(True) 是 'True'，直接用会与 JS/PHP 的 'true' 不一致。"""
    assert build_sign_payload({"flag": True}) == "flag=true"
    assert build_sign_payload({"flag": False}) == "flag=false"


def test_zero_is_kept():
    """0 是有效值，不能被当成空值剔除。"""
    assert build_sign_payload({"n": 0}) == "n=0"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a b", "a%20b"),  # 空格用 %20 而非 +
        ("a/b", "a%2Fb"),  # 斜杠必须编码
        ("a=b", "a%3Db"),
        ("a&b", "a%26b"),
        ("a+b", "a%2Bb"),
        ("a%b", "a%25b"),
    ],
)
def test_value_encoding(raw: str, expected: str):
    assert build_sign_payload({"k": raw}) == f"k={expected}"


@pytest.mark.parametrize("char", list("-_.!~*'()"))
def test_unreserved_chars_are_not_encoded(char: str):
    """这批字符与 JS encodeURIComponent 的保留集一致，不得编码。"""
    assert build_sign_payload({"k": char}) == f"k={char}"


def test_unicode_is_percent_encoded_utf8():
    """中文按 UTF-8 逐字节百分号编码，与 encodeURIComponent 一致。"""
    payload = build_sign_payload({"k": "中"})
    assert payload == "k=%E4%B8%AD"


def test_nested_dict_uses_sorted_compact_json():
    """嵌套结构序列化必须稳定：键排序 + 无空格。"""
    payload = build_sign_payload({"fp": {"b": 2, "a": 1}})
    # {"a":1,"b":2} 编码后：引号 %22，冒号 %3A，逗号 %2C，花括号 %7B/%7D
    assert payload == "fp=%7B%22a%22%3A1%2C%22b%22%3A2%7D"


def test_dict_key_order_does_not_affect_payload():
    """同一结构不同书写顺序必须产出同一待签串。"""
    assert build_sign_payload({"fp": {"a": 1, "b": 2}}) == build_sign_payload(
        {"fp": {"b": 2, "a": 1}}
    )


# ── 签名与验签 ──


def test_sign_verify_roundtrip():
    params = {"app_id": 1, "ip": "203.0.113.1", "timestamp": 1700000000}
    assert verify_params_signature(params, SECRET, sign_params(params, SECRET))


def test_wrong_secret_fails():
    params = {"app_id": 1}
    assert not verify_params_signature(params, "other-secret", sign_params(params, SECRET))


def test_tampered_param_fails():
    params = {"app_id": 1, "ip": "203.0.113.1"}
    sign = sign_params(params, SECRET)
    assert not verify_params_signature({**params, "ip": "198.51.100.9"}, SECRET, sign)


def test_empty_sign_fails():
    assert not verify_params_signature({"a": "1"}, SECRET, "")


def test_sign_is_stable_across_calls():
    params = {"a": "1", "b": "2"}
    assert sign_params(params, SECRET) == sign_params(params, SECRET)


def test_sign_ignores_incoming_sign_field():
    """请求体里带的旧 sign 不得参与新签名计算。"""
    params = {"a": "1"}
    assert sign_params(params, SECRET) == sign_params({**params, "sign": "junk"}, SECRET)


def test_sign_is_64_hex_chars():
    sign = sign_params({"a": "1"}, SECRET)
    assert len(sign) == 64
    assert all(c in "0123456789abcdef" for c in sign)


# ── 时间戳与 nonce ──


def test_timestamp_within_window_is_fresh():
    assert is_timestamp_fresh(1700000000, now=1700000000)
    assert is_timestamp_fresh(1700000000, now=1700000299)


def test_timestamp_tolerates_clock_skew_both_ways():
    """客户端时钟可能快也可能慢，只拦单侧会误杀时钟偏快的正常访客。"""
    assert is_timestamp_fresh(1700000000, now=1699999800)  # 客户端快 200s
    assert is_timestamp_fresh(1700000000, now=1700000200)  # 客户端慢 200s


def test_timestamp_outside_window_is_stale():
    assert not is_timestamp_fresh(1700000000, now=1700000301)
    assert not is_timestamp_fresh(1700000000, now=1699999699)


@pytest.mark.parametrize("bad", [None, "", "abc", [], {}])
def test_malformed_timestamp_is_rejected(bad):
    assert not is_timestamp_fresh(bad, now=1700000000)


def test_string_timestamp_is_accepted():
    """适配器传上来的多为字符串，必须接受。"""
    assert is_timestamp_fresh("1700000000", now=1700000000)


def test_custom_window():
    assert is_timestamp_fresh(1700000000, window=10, now=1700000010)
    assert not is_timestamp_fresh(1700000000, window=10, now=1700000011)


def test_nonce_is_unique_and_hex():
    nonces = {generate_nonce() for _ in range(200)}
    assert len(nonces) == 200
    assert all(len(n) == 32 for n in nonces)
    assert all(c in "0123456789abcdef" for n in nonces for c in n)

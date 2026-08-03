"""待签串跨语言一致性锁。

与 ``client-sdk/tests/signer.test.ts`` 读同一份向量文件。Python 侧是权威实现，
向量由 ``client-sdk/tests/fixtures/gen_vectors.py`` 生成；本测试确保向量文件
没有相对当前实现漂移（例如有人改了 ``build_sign_payload`` 却忘了重新生成）。

两个测试同时存在的意义：改了 Python 实现 → 这里先红；改了 TS 实现 →
vitest 先红。任一侧单独漂移都拦得住。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fangyu_shared.utils.crypto import build_sign_payload, hmac_sha256

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "client-sdk"
    / "tests"
    / "fixtures"
    / "sign_vectors.json"
)


def _load() -> dict:
    if not _FIXTURE.exists():  # pragma: no cover - 仓库完整时不会触发
        pytest.skip(f"向量文件缺失: {_FIXTURE}")
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


_FIXTURE_DATA = _load()
_VECTORS = _FIXTURE_DATA["vectors"]
_SECRET = _FIXTURE_DATA["secret"]


def test_fixture_not_empty() -> None:
    assert len(_VECTORS) >= 10


@pytest.mark.parametrize("vector", _VECTORS, ids=lambda v: v["name"])
def test_payload_matches_fixture(vector: dict) -> None:
    """向量中的待签串与当前实现一致。"""
    assert build_sign_payload(vector["params"]) == vector["payload"]


@pytest.mark.parametrize("vector", _VECTORS, ids=lambda v: v["name"])
def test_signature_matches_fixture(vector: dict) -> None:
    """向量中的签名与当前实现一致。"""
    assert hmac_sha256(_SECRET, vector["payload"]) == vector["sign"]


def test_fixture_covers_critical_encodings() -> None:
    """向量必须覆盖历史上真实踩过的坑，否则等于没锁。"""
    payloads = {v["name"]: v["payload"] for v in _VECTORS}

    # `/` 编码成 %2F —— 两侧对斜杠处理不一致是最常见的验签失败原因
    assert "%2F" in payloads["slash_is_encoded"]
    # 空格是 %20 不是 +
    assert "%20" in payloads["space_is_percent20"]
    assert "+" not in payloads["space_is_percent20"]
    # bool 小写
    assert payloads["bool_lowercase"] == "flag_off=false&flag_on=true"
    # 0 / false 保留，None / 空串剔除
    assert payloads["drops_none_and_empty_string"] == "a=1&d=0&e=false"
    # sign 自身不参与签名
    assert payloads["sign_key_excluded"] == "a=1"
    # safe 字符集原样保留
    assert payloads["reserved_chars_preserved"] == "token=-_.!~*'()"
    # 非 ASCII 走 UTF-8 百分号编码
    assert "%E9%98%B2" in payloads["unicode_percent_encoded_utf8"]


def test_nested_json_keys_are_sorted() -> None:
    """嵌套结构的键必须排序，否则 JS 的插入序会与 Python 不一致。"""
    payload = build_sign_payload({"fp": {"b": 2, "a": 1}})
    assert payload == "fp=%7B%22a%22%3A1%2C%22b%22%3A2%7D"


def test_list_order_is_preserved() -> None:
    """list 保序：顺序本身是语义（行为事件的时序）。"""
    first = build_sign_payload({"e": [1, 2, 3]})
    second = build_sign_payload({"e": [3, 2, 1]})
    assert first != second

"""生成待签串парity 向量。

由 Python 侧的 ``build_sign_payload`` 权威产出，TS 侧测试读取同一份文件断言
逐字节一致。**不要手写这个 JSON**——手写等于放弃了「以 Python 实现为准」。

用法（在 shared 包可导入的环境下）::

    python client-sdk/tests/fixtures/gen_vectors.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fangyu_shared.utils.crypto import build_sign_payload, hmac_sha256

SECRET = "test_secret_do_not_use_in_production"

CASES: list[dict] = [
    {
        "name": "basic_sorted_keys",
        "note": "键按字典序排列，不是插入序",
        "params": {"zebra": "z", "alpha": "a", "middle": "m"},
    },
    {
        "name": "drops_none_and_empty_string",
        "note": "None 与空串剔除；0 与 false 保留",
        "params": {"a": 1, "b": None, "c": "", "d": 0, "e": False},
    },
    {
        "name": "bool_lowercase",
        "note": "bool 转小写 true/false，不是 Python 的 True/False",
        "params": {"flag_on": True, "flag_off": False},
    },
    {
        "name": "slash_is_encoded",
        "note": "/ 必须编码成 %2F —— 最常见的验签失败原因",
        "params": {"visitUrl": "https://example.com/a/b?x=1&y=2"},
    },
    {
        "name": "space_is_percent20",
        "note": "空格编码成 %20，不是 +",
        "params": {"userAgent": "Mozilla/5.0 (Windows NT 10.0)"},
    },
    {
        "name": "nested_dict_sorted_compact_json",
        "note": "嵌套 dict 用键排序的紧凑 JSON",
        "params": {"fp": {"b": 2, "a": 1, "c": {"z": 26, "y": 25}}},
    },
    {
        "name": "nested_list_preserves_order",
        "note": "list 保序，元素内的 dict 仍然排序",
        "params": {"events": [{"kind": "click", "ts": 3}, {"ts": 1, "kind": "scroll"}]},
    },
    {
        "name": "sign_key_excluded",
        "note": "sign 字段自身不参与签名",
        "params": {"a": 1, "sign": "deadbeef"},
    },
    {
        "name": "unicode_percent_encoded_utf8",
        "note": "非 ASCII 按 UTF-8 字节百分号编码",
        "params": {"name": "防御系统", "emoji": "🛡"},
    },
    {
        "name": "reserved_chars_preserved",
        "note": "-_.!~*'() 是 safe 集，保持原样",
        "params": {"token": "-_.!~*'()"},
    },
    {
        "name": "decide_body_shape",
        "note": "真实 /v2/decide 顶层签名参数形状",
        "params": {
            "context": {
                "appId": 1,
                "ingress": "sdk",
                "fingerprint": "abc123",
                "userAgent": "Mozilla/5.0",
                "visitUrl": "https://shop.example.com/checkout",
                "repeatKey": "_sd_0000",
                "evercookieRestored": True,
                "behaviorEvents": [
                    {"kind": "click", "clientTsMs": 1700000000000, "data": {"x": 10, "y": 20}}
                ],
            },
            "requireDetails": False,
            "timestamp": 1700000000,
            "nonce": "0123456789abcdef0123456789abcdef",
        },
    },
]


def main() -> None:
    vectors = []
    for case in CASES:
        payload = build_sign_payload(case["params"])
        vectors.append(
            {
                "name": case["name"],
                "note": case["note"],
                "params": case["params"],
                "payload": payload,
                "sign": hmac_sha256(SECRET, payload),
            }
        )

    out = Path(__file__).with_name("sign_vectors.json")
    out.write_text(
        json.dumps({"secret": SECRET, "vectors": vectors}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(vectors)} vectors -> {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fangyu Defense — Lua 签名算法一致性验证脚本

用途:
    生成测试向量，验证 Lua 版本的签名实现与 Python 版本完全一致
    
运行:
    python tests/adapters/test_lua_signature.py
    
环境要求:
    - Python 3.11+
    - fangyu_shared 包已安装
"""

import json
import hmac
import hashlib
from typing import Any, Dict
from urllib.parse import quote


def encode_component(s: str) -> str:
    """
    模拟 JavaScript encodeURIComponent 行为
    
    与标准 urllib.parse.quote 的区别:
    - 不编码: - _ . ! ~ * ' ( )
    - 空格编码为 %20 (不是 +)
    """
    # safe 参数指定不编码的字符
    return quote(str(s), safe="-_.!~*'()")


def stringify_value(val: Any) -> str:
    """将值转为字符串（与 Lua 版本对齐）"""
    if isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, dict) or isinstance(val, list):
        # 使用 canonical JSON（排序键）
        return json.dumps(val, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    else:
        return str(val)


def build_payload(params: Dict[str, Any]) -> str:
    """
    构建签名载荷（与 Lua 版本 build_payload 完全一致）
    
    规则:
    1. 排除 "sign" 字段
    2. 过滤 None 和空字符串
    3. 键按字典序排序
    4. 格式: key1=value1&key2=value2
    5. key 和 value 都需要 URL 编码
    """
    excluded_keys = {"sign"}
    
    # 收集并排序键
    sorted_keys = sorted(
        k for k in params.keys() 
        if k not in excluded_keys and params[k] is not None and params[k] != ""
    )
    
    # 构建键值对
    parts = []
    for key in sorted_keys:
        value = params[key]
        # 注意: false (布尔) 必须保留，只有 None 和 "" 被过滤
        encoded_key = encode_component(key)
        encoded_value = encode_component(stringify_value(value))
        parts.append(f"{encoded_key}={encoded_value}")
    
    return "&".join(parts)


def compute_hmac_sha256(secret: str, message: str) -> str:
    """计算 HMAC-SHA256 签名（返回小写十六进制）"""
    return hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def generate_test_vectors():
    """生成测试向量，供 Lua 脚本验证"""
    test_cases = [
        {
            "name": "基础测试 - 简单参数",
            "params": {
                "timestamp": 1700000000,
                "nonce": "aaaa",
                "context": {"ip": "1.1.1.1"},
            },
            "secret": "test_secret",
        },
        {
            "name": "复杂对象 - 嵌套结构",
            "params": {
                "timestamp": 1700000000,
                "nonce": "bbbb",
                "context": {
                    "ip": "2.2.2.2",
                    "userAgent": "Mozilla/5.0",
                    "referer": "https://example.com/page?foo=bar",
                    "extra": {"key1": "value1", "key2": 123},
                },
                "requireDetails": False,
            },
            "secret": "another_secret",
        },
        {
            "name": "特殊字符测试",
            "params": {
                "timestamp": 1700000001,
                "nonce": "cccc",
                "context": {
                    "path": "/api/v2/测试?param=值&other=!@#$%",
                    "userAgent": "Bot/1.0 (compatible; +http://example.com)",
                },
            },
            "secret": "secret_with_中文",
        },
        {
            "name": "边界值测试 - 空对象和布尔值",
            "params": {
                "timestamp": 1700000002,
                "nonce": "dddd",
                "context": {},
                "requireDetails": False,  # 明确的 false 应该保留
                "emptyString": "",  # 应该被过滤
            },
            "secret": "test",
        },
        {
            "name": "数组测试",
            "params": {
                "timestamp": 1700000003,
                "nonce": "eeee",
                "context": {
                    "tags": ["bot", "suspicious", "crawler"],
                    "scores": [0.8, 0.6, 0.9],
                },
            },
            "secret": "array_test",
        },
    ]
    
    results = []
    
    print("=" * 70)
    print("Fangyu 签名算法测试向量生成器")
    print("=" * 70)
    print()
    
    for i, tc in enumerate(test_cases, 1):
        print(f"[测试 {i}] {tc['name']}")
        print("-" * 70)
        
        params = tc["params"]
        secret = tc["secret"]
        
        # 构建载荷
        payload = build_payload(params)
        
        # 计算签名
        signature = compute_hmac_sha256(secret, payload)
        
        # 输出结果
        print(f"参数: {json.dumps(params, ensure_ascii=False, indent=2)}")
        print(f"密钥: {secret}")
        print(f"载荷: {payload}")
        print(f"签名: {signature}")
        print()
        
        results.append({
            "name": tc["name"],
            "params": params,
            "secret": secret,
            "expected_payload": payload,
            "expected_signature": signature,
        })
    
    # 保存为 JSON 文件
    output_file = "tests/adapters/lua_signature_vectors.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("=" * 70)
    print(f"✓ 测试向量已保存到: {output_file}")
    print(f"✓ 共生成 {len(results)} 个测试用例")
    print()
    print("使用方法:")
    print("  1. 在 Lua 中读取该 JSON 文件")
    print("  2. 对每个用例调用 build_payload() 和 compute_hmac()")
    print("  3. 对比 expected_payload 和 expected_signature")
    print("=" * 70)


def verify_against_shared_module():
    """
    使用 fangyu_shared 模块验证签名一致性
    
    仅在 fangyu_shared 包可用时运行
    """
    try:
        from fangyu_shared.security.signing import build_sign_payload, sign_request
    except ImportError:
        print("⚠ fangyu_shared 模块未安装，跳过验证")
        return
    
    print()
    print("=" * 70)
    print("与 fangyu_shared 模块对比验证")
    print("=" * 70)
    print()
    
    test_params = {
        "timestamp": 1700000000,
        "nonce": "test_nonce",
        "context": {"ip": "1.1.1.1", "siteId": "site_123"},
        "requireDetails": False,
    }
    secret = "shared_secret"
    
    # 本脚本实现
    payload_local = build_payload(test_params)
    sign_local = compute_hmac_sha256(secret, payload_local)
    
    # fangyu_shared 实现
    payload_shared = build_sign_payload(test_params)
    sign_shared = sign_request(test_params, secret)
    
    print(f"本脚本载荷: {payload_local}")
    print(f"共享模块载荷: {payload_shared}")
    print(f"载荷匹配: {'✓' if payload_local == payload_shared else '✗'}")
    print()
    print(f"本脚本签名: {sign_local}")
    print(f"共享模块签名: {sign_shared}")
    print(f"签名匹配: {'✓' if sign_local == sign_shared else '✗'}")
    print()
    
    if payload_local == payload_shared and sign_local == sign_shared:
        print("✓ 验证通过！本脚本与 fangyu_shared 模块完全一致")
    else:
        print("✗ 验证失败！存在不一致")
        exit(1)


def main():
    """主函数"""
    generate_test_vectors()
    verify_against_shared_module()
    
    print()
    print("下一步:")
    print("  1. 将 lua_signature_vectors.json 复制到服务器")
    print("  2. 编写 Lua 测试脚本读取并验证")
    print("  3. 或使用 tests/adapters/test_openresty_deployment.sh 自动测试")


if __name__ == "__main__":
    main()

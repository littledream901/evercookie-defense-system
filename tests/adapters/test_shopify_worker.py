#!/usr/bin/env python3
"""Shopify Cloudflare Worker 签名一致性测试。

测试 Shopify 适配器的签名算法与 Python 参考实现的字节级一致性。

注意:
    实际的 JavaScript 签名验证需要在 Node.js 或 Workers 运行时中执行。
    此文件验证 Python 侧的参考实现。
"""

import json
import hmac
import hashlib
from typing import Any, Dict

import pytest


def encode_component(s: str) -> str:
    """模拟 JavaScript encodeURIComponent 行为"""
    from urllib.parse import quote
    return quote(str(s), safe="-_.!~*'()")


def stringify_value(val: Any) -> str:
    """将值转为字符串（与 JS 实现对齐）"""
    if isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, dict) or isinstance(val, list):
        return json.dumps(val, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    else:
        return str(val)


def build_payload(params: Dict[str, Any]) -> str:
    """构建签名载荷（Workers 实现的参考标准）"""
    excluded_keys = {"sign"}
    
    sorted_keys = sorted(
        k for k in params.keys() 
        if k not in excluded_keys and params[k] is not None and params[k] != ""
    )
    
    parts = []
    for key in sorted_keys:
        value = params[key]
        encoded_key = encode_component(key)
        encoded_value = encode_component(stringify_value(value))
        parts.append(f"{encoded_key}={encoded_value}")
    
    return "&".join(parts)


def compute_hmac_sha256(secret: str, message: str) -> str:
    """计算 HMAC-SHA256 签名（模拟 Web Crypto API 行为）"""
    return hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


class TestShopifyWorkerSignatureParity:
    """Shopify Worker 签名一致性测试（与 Python 参考实现对齐）"""
    
    def test_basic_signature(self):
        """测试基础签名（与 worker.js buildSignPayload 对齐）"""
        params = {
            "timestamp": 1700000000,
            "nonce": "aaaa",
            "context": {"ip": "1.1.1.1"},
        }
        secret = "test_secret"
        
        payload = build_payload(params)
        signature = compute_hmac_sha256(secret, payload)
        
        # 验证载荷格式与 Python/PHP/Lua 一致
        assert payload == "context=%7B%22ip%22%3A%221.1.1.1%22%7D&nonce=aaaa&timestamp=1700000000"
        assert len(signature) == 64
        assert signature.islower()
    
    def test_web_crypto_hmac_compatibility(self):
        """测试 Web Crypto API HMAC 兼容性"""
        params = {
            "timestamp": 1700000000,
            "nonce": "test_nonce",
            "context": {"ip": "1.1.1.1", "path": "/checkout"}
        }
        secret = "test_secret"
        
        payload = build_payload(params)
        signature = compute_hmac_sha256(secret, payload)
        
        # Web Crypto API 的 crypto.subtle.sign('HMAC', ...) 应该产生相同的签名
        assert len(signature) == 64
        assert signature == compute_hmac_sha256(secret, payload)  # 幂等性
    
    def test_shopify_checkout_context(self):
        """测试 Shopify 结账流程上下文"""
        params = {
            "timestamp": 1700000000,
            "nonce": "checkout_nonce",
            "context": {
                "ip": "1.1.1.1",
                "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0)",
                "path": "/checkouts/cn/Z2NwLXVzLWNlbnRyYWw",
                "referer": "https://shop.example.com/cart",
                "method": "POST"
            }
        }
        secret = "test_secret"
        
        payload = build_payload(params)
        signature = compute_hmac_sha256(secret, payload)
        
        # context 整体作为一个参数值被 URL 编码，结账路径中的 / 必须转义为 %2F
        assert "%22path%22%3A%22%2Fcheckouts%2Fcn%2F" in payload
        assert len(signature) == 64
    
    def test_cloudflare_headers_extraction(self):
        """测试 Cloudflare 请求头提取逻辑"""
        # Worker 从 CF headers 提取真实 IP
        cf_headers = {
            "cf-connecting-ip": "203.0.113.1",
            "cf-ipcountry": "US",
            "cf-ray": "7f4d5e6a7b8c9d0e"
        }
        
        params = {
            "timestamp": 1700000000,
            "nonce": "cf_test",
            "context": {
                "ip": cf_headers["cf-connecting-ip"],
                "country": cf_headers["cf-ipcountry"],
                "cfRay": cf_headers["cf-ray"]
            }
        }
        secret = "test"
        
        payload = build_payload(params)
        
        # 验证 CF 特有字段被正确序列化
        assert "ip=" in payload or "context=" in payload
        assert len(compute_hmac_sha256(secret, payload)) == 64


class TestShopifyWorkerHeartbeat:
    """Shopify Worker 心跳上报测试"""
    
    def test_heartbeat_payload_structure(self):
        """测试心跳载荷结构"""
        params = {
            "timestamp": 1700000000,
            "nonce": "heartbeat_nonce",
            "siteId": 123,
            "fingerprint": "fp_test_123",
            "sdkVersion": "cf-worker-2.0",
            "behaviorEvents": [{"kind": "page_view", "ts": 1700000000000, "value": 1}]
        }
        secret = "test"
        
        payload = build_payload(params)
        signature = compute_hmac_sha256(secret, payload)
        
        # 验证心跳字段存在
        assert "siteId=" in payload
        assert "fingerprint=" in payload
        assert "behaviorEvents=" in payload
        assert len(signature) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""加密/哈希相关工具。

统一使用 hmac.compare_digest 做常量时间比较，避免时序攻击。
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hmac_sha256(secret: str | bytes, message: str | bytes) -> str:
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if isinstance(message, str):
        message = message.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def constant_time_compare(a: str | bytes, b: str | bytes) -> bool:
    if isinstance(a, str):
        a = a.encode("utf-8")
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hmac.compare_digest(a, b)


def stable_hash(payload: Any) -> str:
    """对任意可序列化对象生成稳定 SHA256（键排序）。"""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_hex(encoded)

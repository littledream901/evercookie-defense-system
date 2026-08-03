"""加密/哈希相关工具。

统一使用 hmac.compare_digest 做常量时间比较，避免时序攻击。

签名规范
--------
:func:`build_sign_payload` 是**全系统唯一**的待签串构造实现。gateway 验签、
client-sdk 签名、WordPress / nginx-lua / Cloudflare Worker 适配器、以及测试
页面都必须产出逐字节一致的结果，否则验签必然失败。

编码用 ``quote(safe="-_.!~*'()")``，对齐 JS ``encodeURIComponent`` 的保留
字符集，让浏览器侧无需做差异映射。注意 ``/`` **会**被编码成 ``%2F``
（Python ``quote`` 默认 safe 含 ``/``，这里显式排除）：``visit_url`` 之类的
值里带路径，两侧对 ``/`` 处理不一致是最常见的验签失败原因。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from urllib.parse import quote

SIGN_SAFE_CHARS = "-_.!~*'()"
"""待签串的 URL 编码保留字符集，对齐 JS encodeURIComponent。"""

DEFAULT_TIMESTAMP_WINDOW = 300
"""时间戳容忍窗口（秒）。与 nonce TTL 一致，两者共同界定重放窗口。"""

_SIGN_EXCLUDED_KEYS = frozenset({"sign"})
"""不参与签名的字段。"""


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


def _sign_value(value: Any) -> str:
    """把单个参数值转成待签字符串。

    dict / list 用紧凑且键排序的 JSON，保证同一结构在任何语言里序列化一致。
    bool 用小写 ``true`` / ``false``，对齐 JS 与 PHP 的字符串化行为
    （Python ``str(True)`` 是 ``"True"``，直接用会两侧不一致）。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def build_sign_payload(params: dict[str, Any]) -> str:
    """构造待签串：键字典序 → URL 编码 → ``k=v&k=v``。

    ``None`` 值与空字符串一并剔除。适配器侧（PHP / Lua / JS）对「字段缺失」
    和「字段为空串」的表达不统一，若参与签名会导致同一请求在不同接入方
    算出不同签名。

    Args:
        params: 参数字典，不含 ``sign``。

    Returns:
        待签字符串。
    """
    parts = []
    for key in sorted(params):
        if key in _SIGN_EXCLUDED_KEYS:
            continue
        value = params[key]
        if value is None or value == "":
            continue
        encoded_key = quote(str(key), safe=SIGN_SAFE_CHARS)
        encoded_value = quote(_sign_value(value), safe=SIGN_SAFE_CHARS)
        parts.append(f"{encoded_key}={encoded_value}")
    return "&".join(parts)


def sign_params(params: dict[str, Any], secret: str) -> str:
    """对参数字典生成 HMAC-SHA256 签名。"""
    return hmac_sha256(secret, build_sign_payload(params))


def verify_params_signature(params: dict[str, Any], secret: str, sign: str) -> bool:
    """验证参数签名。常量时间比较。"""
    if not sign:
        return False
    return constant_time_compare(sign_params(params, secret), sign)


def generate_nonce() -> str:
    """生成 32 位十六进制随机 nonce。"""
    return secrets.token_hex(16)


def is_timestamp_fresh(
    timestamp: int | str | None,
    *,
    window: int = DEFAULT_TIMESTAMP_WINDOW,
    now: int | None = None,
) -> bool:
    """判断时间戳是否落在容忍窗口内（秒级 Unix 时间戳）。

    双向容忍：客户端时钟可能快也可能慢，只拦单侧会把时钟偏快的正常访客
    全部误杀。
    """
    if timestamp is None or timestamp == "":
        return False
    try:
        ts = int(float(timestamp))
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    return abs(current - ts) <= window

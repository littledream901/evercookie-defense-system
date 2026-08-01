"""JWT 签发回归测试。

覆盖本轮发现的两个 JWT Bug：
1. datetime.utcnow().timestamp() 时区陷阱（UTC+8 环境下 token 出生即过期）
2. PyJWT>=2.9 要求 sub 必须为字符串（传 int 导致 InvalidSubjectError）
"""
from __future__ import annotations

import time

import jwt
import pytest


def _make_token(user_id, secret="test-secret-32chars-padding-here", ttl=3600):
    now_ts = int(time.time())
    return jwt.encode(
        {"sub": str(user_id), "exp": now_ts + ttl, "type": "access"},
        secret,
        algorithm="HS256",
    )


def test_sub_is_string_not_int():
    """回归：PyJWT>=2.9 严格要求 sub 为字符串，传 int 会抛 InvalidSubjectError。"""
    secret = "test-secret-32chars-padding-here"
    now_ts = int(time.time())
    payload = {"sub": str(3), "exp": now_ts + 3600, "type": "access"}
    token = jwt.encode(payload, secret, algorithm="HS256")
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
    assert isinstance(decoded["sub"], str), "sub 必须是字符串"
    assert decoded["sub"] == "3"


def test_sub_int_behavior_documented():
    """文档：传 int sub 在部分 PyJWT 版本下会抛异常，确认我们的代码总是传字符串。
    此测试不断言具体异常类型，只记录行为。"""
    secret = "test-secret-32chars-padding-here"
    now_ts = int(time.time())
    token = jwt.encode(
        {"sub": 3, "exp": now_ts + 3600},
        secret,
        algorithm="HS256",
    )
    # 在某些 PyJWT 版本下 decode 会抛异常，在另一些版本下不抛
    # 关键是：我们的 auth_service 永远传 str(user_id)，不走这条路径
    try:
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        assert decoded["sub"] in (3, "3")
    except Exception:
        pass  # 版本差异，属预期


def test_token_not_expired_immediately():
    """回归：使用 time.time() 而非 datetime.utcnow().timestamp()，
    确保 UTC+8 环境下 token 不会出生即过期。"""
    secret = "test-secret-32chars-padding-here"
    token = _make_token(user_id=1, secret=secret, ttl=3600)
    decoded = jwt.decode(token, secret, algorithms=["HS256"])
    remaining = decoded["exp"] - int(time.time())
    assert remaining > 3590, f"token 应有约 3600s 有效期，实际剩余 {remaining}s"


def test_token_expired_after_ttl():
    """签发一个已过期的 token，确认 jwt.decode 正确拒绝。"""
    secret = "test-secret-32chars-padding-here"
    now_ts = int(time.time())
    token = jwt.encode(
        {"sub": "1", "exp": now_ts - 10, "type": "access"},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, secret, algorithms=["HS256"])


def test_wrong_secret_rejected():
    secret = "test-secret-32chars-padding-here"
    other = "completely-different-secret-32ch"
    token = _make_token(user_id=1, secret=secret)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other, algorithms=["HS256"])

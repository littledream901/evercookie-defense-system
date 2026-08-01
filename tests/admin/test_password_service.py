"""PasswordService 回归测试。

覆盖 passlib/bcrypt 不兼容 Bug 的修复：
- passlib 1.7.x 与 bcrypt>=4.1 不兼容（__about__ 被移除）
- 现在直接使用 bcrypt 原生 API，不经 passlib
"""
from __future__ import annotations

import sys
import types

import pytest

import src.domain.user.password as pw_module
from src.domain.user.password import PasswordService


def test_hash_returns_bcrypt_prefix():
    svc = PasswordService()
    h = svc.hash("Admin@2026")
    assert h.startswith(("$2a$", "$2b$", "$2y$")), "应是 bcrypt 格式"


def test_verify_correct_password():
    svc = PasswordService()
    h = svc.hash("Admin@2026")
    assert svc.verify("Admin@2026", h) is True


def test_verify_wrong_password():
    svc = PasswordService()
    h = svc.hash("Admin@2026")
    assert svc.verify("wrong-password", h) is False


def test_verify_empty_values():
    svc = PasswordService()
    assert svc.verify("", "somehash") is False
    assert svc.verify("Admin@2026", "") is False


def test_verify_corrupt_hash_does_not_raise():
    svc = PasswordService()
    assert svc.verify("Admin@2026", "not-a-bcrypt-hash") is False


def test_password_service_does_not_import_passlib():
    """回归：不再依赖 passlib，避免与 bcrypt>=4.1 的不兼容崩溃。"""
    assert "passlib" not in sys.modules.get("src.domain.user.password", types.ModuleType("")).__dict__.get(
        "__module__", ""
    ), "passlib 不应被 password.py 使用"
    import importlib
    spec = importlib.util.find_spec("passlib")
    if spec is not None:
        assert not hasattr(pw_module, "CryptContext"), "password 模块不应暴露 CryptContext"


def test_hash_strength_validation():
    svc = PasswordService()
    with pytest.raises(ValueError, match="8"):
        svc.hash("short")
    with pytest.raises(ValueError, match="대문자|大写|uppercase|[Uu]pper"):
        svc.hash("alllower1")
    with pytest.raises(ValueError, match="소문자|小写|lowercase|[Ll]ower"):
        svc.hash("ALLUPPER1")
    with pytest.raises(ValueError, match="숫자|数字|digit|[Dd]igit"):
        svc.hash("NoNumbers!")


def test_needs_rehash_fresh_hash():
    svc = PasswordService()
    h = svc.hash("Admin@2026")
    assert svc.needs_rehash(h) is False


def test_needs_rehash_plain_text():
    svc = PasswordService()
    assert svc.needs_rehash("plain-text") is True

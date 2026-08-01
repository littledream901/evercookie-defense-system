"""fangyu_shared.exceptions.business 单元测试。"""
from __future__ import annotations

import pytest

from fangyu_shared.exceptions import (
    AuthenticationException,
    BusinessRuleException,
    ConflictException,
    PermissionDeniedException,
    RateLimitException,
    ResourceNotFoundException,
    ValidationException,
)


class TestResourceNotFoundException:
    def test_simple_message_form(self):
        exc = ResourceNotFoundException("用户不存在: 42")
        assert exc.message == "用户不存在: 42"
        assert exc.status_code == 404

    def test_structured_form(self):
        exc = ResourceNotFoundException("用户", 42)
        assert "42" in exc.message
        assert exc.details["resource_id"] == "42"
        assert exc.details["resource_type"] == "用户"
        assert exc.code == "用户_NOT_FOUND"


class TestValidationException:
    def test_simple_message_form(self):
        exc = ValidationException("密码长度不能少于 8 位")
        assert exc.message == "密码长度不能少于 8 位"
        assert exc.status_code == 422

    def test_structured_form(self):
        exc = ValidationException("password", "过短", value="abc")
        assert exc.details == {"field": "password", "reason": "过短", "value": "abc"}


class TestPermissionDeniedException:
    def test_from_permission_code(self):
        exc = PermissionDeniedException("user.write")
        assert exc.status_code == 403
        assert exc.details["required_permission"] == "user.write"
        assert "user.write" in exc.message

    def test_custom_message_only(self):
        exc = PermissionDeniedException(message="超出租户范围")
        assert exc.message == "超出租户范围"
        assert exc.status_code == 403


class TestOthers:
    def test_authentication(self):
        exc = AuthenticationException()
        assert exc.status_code == 401

    def test_conflict(self):
        exc = ConflictException("用户名已存在")
        assert exc.status_code == 409

    def test_business_rule(self):
        exc = BusinessRuleException("规则不允许由 archived -> published")
        assert exc.status_code == 409

    def test_rate_limit_with_retry(self):
        exc = RateLimitException(retry_after=30)
        assert exc.status_code == 429
        assert exc.details["retry_after_seconds"] == 30

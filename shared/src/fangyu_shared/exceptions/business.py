"""业务异常子类库."""

from __future__ import annotations

from typing import Any

from .base import BusinessException


class ResourceNotFoundException(BusinessException):
    default_code = "RES_NOT_FOUND"
    default_status = 404

    def __init__(
        self,
        resource_type: str,
        resource_id: str | int | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        if resource_id is None:
            # 简化用法：ResourceNotFoundException("用户不存在: 12")
            super().__init__(message=resource_type, details=details or {})
            return
        merged: dict[str, Any] = {
            "resource_type": resource_type,
            "resource_id": str(resource_id),
        }
        if details:
            merged.update(details)
        super().__init__(
            message=f"{resource_type} `{resource_id}` 不存在",
            code=f"{resource_type.upper()}_NOT_FOUND",
            details=merged,
        )


class PermissionDeniedException(BusinessException):
    default_code = "PERM_DENIED"
    default_status = 403

    def __init__(
        self,
        permission: str | None = None,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        final_message = message or (
            f"缺少权限: {permission}" if permission else "权限不足"
        )
        merged: dict[str, Any] = {}
        if permission:
            merged["required_permission"] = permission
        if details:
            merged.update(details)
        super().__init__(message=final_message, details=merged)


class AuthenticationException(BusinessException):
    default_code = "AUTH_UNAUTHENTICATED"
    default_status = 401

    def __init__(self, message: str = "身份未认证或已过期") -> None:
        super().__init__(message=message)


class ValidationException(BusinessException):
    default_code = "VALID_FAILED"
    default_status = 422

    def __init__(
        self,
        field: str,
        reason: str | None = None,
        value: Any = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        if reason is None:
            # 简化用法：ValidationException("密码长度不能少于 8 位")
            super().__init__(message=field, details=details or {})
            return
        merged: dict[str, Any] = {"field": field, "reason": reason, "value": value}
        if details:
            merged.update(details)
        super().__init__(message=f"参数校验失败: {field} - {reason}", details=merged)


class ConflictException(BusinessException):
    default_code = "RES_CONFLICT"
    default_status = 409

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


class BusinessRuleException(BusinessException):
    """业务规则不允许当前操作（状态机、约束等）。"""

    default_code = "BUSINESS_RULE_VIOLATION"
    default_status = 409

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


class RateLimitException(BusinessException):
    default_code = "RATE_LIMIT_EXCEEDED"
    default_status = 429

    def __init__(self, retry_after: int | None = None) -> None:
        super().__init__(
            message="请求过于频繁，请稍后再试",
            details={"retry_after_seconds": retry_after} if retry_after else {},
        )


class ExternalServiceException(BusinessException):
    default_code = "EXTERNAL_SERVICE_ERROR"
    default_status = 502

    def __init__(self, service: str, reason: str) -> None:
        super().__init__(
            message=f"外部服务 {service} 调用失败: {reason}",
            details={"service": service, "reason": reason},
        )

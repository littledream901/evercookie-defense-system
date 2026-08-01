"""统一业务异常与 FastAPI 处理器."""

from .base import BusinessException
from .business import (
    AuthenticationException,
    BusinessRuleException,
    ConflictException,
    ExternalServiceException,
    PermissionDeniedException,
    RateLimitException,
    ResourceNotFoundException,
    ValidationException,
)
from .handlers import register_exception_handlers

__all__ = [
    "AuthenticationException",
    "BusinessException",
    "BusinessRuleException",
    "ConflictException",
    "ExternalServiceException",
    "PermissionDeniedException",
    "RateLimitException",
    "ResourceNotFoundException",
    "ValidationException",
    "register_exception_handlers",
]

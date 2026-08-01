"""业务异常基类."""

from __future__ import annotations

from typing import Any


class BusinessException(Exception):
    """业务异常基类，所有子类必须提供错误码与消息."""

    default_code: str = "INTERNAL_UNKNOWN"
    default_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code or self.default_code
        self.status_code = status_code or self.default_status
        self.details: dict[str, Any] = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """转成前端友好的字典结构."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

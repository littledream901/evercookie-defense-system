"""通用响应/分页 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        from_attributes=True,
    )


class SuccessResponse(BaseSchema, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
    request_id: str | None = None


class ErrorResponse(BaseSchema):
    code: str = "INTERNAL_UNKNOWN"
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class PageRequest(BaseSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=500, alias="pageSize")


class PageResponse(BaseSchema, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = Field(default=20, alias="pageSize")


class HealthCheckResponse(BaseSchema):
    service: str
    status: str = "ok"
    version: str | None = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    dependencies: dict[str, str] = Field(default_factory=dict)

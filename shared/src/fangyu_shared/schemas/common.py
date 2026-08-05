"""通用响应/分页 Schema。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer

T = TypeVar("T")


def _iso_utc(value: datetime | None) -> str | None:
    """将 datetime 统一序列化为带 Z 后缀的 UTC ISO 字符串。

    naive datetime 视为 UTC（因为 MySQL 会话时区已设为 UTC，读回的
    DateTime 列没有 tzinfo，但值本身是 UTC）；aware datetime 转成 UTC 输出。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        from_attributes=True,
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_datetime(self, value):  # noqa: D401
        if isinstance(value, datetime):
            return _iso_utc(value)
        return value


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
    checked_at: datetime
    dependencies: dict[str, str] = Field(default_factory=dict)

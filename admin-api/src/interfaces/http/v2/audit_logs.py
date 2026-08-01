"""审计日志查询路由。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.application.services.audit_service import AuditService
from src.domain.audit.entities import AuditLog
from src.interfaces.http.dependencies import (
    get_audit_service,
    require_permission,
)

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


class AuditLogSchema(BaseModel):
    id: int | None = None
    occurred_at: datetime = Field(..., alias="occurredAt")
    user_id: int | None = Field(default=None, alias="userId")
    username: str = ""
    method: str = ""
    path: str = ""
    resource: str = ""
    resource_id: str = Field(default="", alias="resourceId")
    action: str = ""
    status_code: int = Field(default=0, alias="statusCode")
    ip: str = ""
    user_agent: str = Field(default="", alias="userAgent")
    request_id: str = Field(default="", alias="requestId")
    detail: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


def _to_schema(log: AuditLog) -> AuditLogSchema:
    return AuditLogSchema(
        id=log.id,
        occurredAt=log.occurred_at,
        userId=log.user_id,
        username=log.username,
        method=log.method,
        path=log.path,
        resource=log.resource,
        resourceId=log.resource_id,
        action=log.action,
        statusCode=log.status_code,
        ip=log.ip,
        userAgent=log.user_agent,
        requestId=log.request_id,
        detail=log.detail,
    )


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[AuditLogSchema]],
    dependencies=[Depends(require_permission("audit.read"))],
)
async def list_audit_logs(
    user_id: int | None = Query(default=None, alias="userId"),
    resource: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=32),
    start_at: datetime | None = Query(default=None, alias="startAt"),
    end_at: datetime | None = Query(default=None, alias="endAt"),
    keyword: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    service: AuditService = Depends(get_audit_service),
) -> SuccessResponse[PageResponse[AuditLogSchema]]:
    items, total = await service.list_paged(
        user_id=user_id,
        resource=resource,
        action=action,
        start_at=start_at,
        end_at=end_at,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    page_data = PageResponse[AuditLogSchema](
        items=[_to_schema(log) for log in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return SuccessResponse[PageResponse[AuditLogSchema]](data=page_data)

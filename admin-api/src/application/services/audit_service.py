"""审计日志服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fangyu_shared.logging import get_logger
from fangyu_shared.utils.time import utcnow

from src.domain.audit.entities import AuditAction, AuditLog
from src.infrastructure.repositories.audit_repository import AuditLogRepository

_logger = get_logger("admin.audit_service")


class AuditService:
    def __init__(self, repo: AuditLogRepository) -> None:
        self._repo = repo

    async def record(
        self,
        *,
        user_id: int | None,
        username: str = "",
        method: str = "",
        path: str = "",
        resource: str = "",
        resource_id: str = "",
        action: str = AuditAction.OTHER.value,
        status_code: int = 0,
        ip: str = "",
        user_agent: str = "",
        request_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        log = AuditLog(
            occurred_at=utcnow(),
            user_id=user_id,
            username=username,
            method=method,
            path=path,
            resource=resource,
            resource_id=resource_id,
            action=action,
            status_code=status_code,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            detail=detail,
        )
        return await self._repo.create(log)

    async def list_paged(
        self,
        *,
        user_id: int | None,
        resource: str | None,
        action: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AuditLog], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_paged(
            user_id=user_id,
            resource=resource,
            action=action,
            start_at=start_at,
            end_at=end_at,
            keyword=keyword,
            offset=offset,
            limit=page_size,
        )

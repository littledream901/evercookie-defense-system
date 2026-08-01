"""审计日志仓储。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.audit.entities import AuditLog
from src.infrastructure.repositories.models import AuditLogModel


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, log: AuditLog) -> AuditLog:
        model = AuditLogModel(
            occurred_at=log.occurred_at,
            user_id=log.user_id,
            username=log.username,
            method=log.method,
            path=log.path,
            resource=log.resource,
            resource_id=log.resource_id,
            action=log.action,
            status_code=log.status_code,
            ip=log.ip,
            user_agent=log.user_agent,
            request_id=log.request_id,
            detail=log.detail,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def list_paged(
        self,
        *,
        user_id: int | None = None,
        resource: str | None = None,
        action: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AuditLog], int]:
        conds = []
        if user_id is not None:
            conds.append(AuditLogModel.user_id == user_id)
        if resource:
            conds.append(AuditLogModel.resource == resource)
        if action:
            conds.append(AuditLogModel.action == action)
        if start_at is not None:
            conds.append(AuditLogModel.occurred_at >= start_at)
        if end_at is not None:
            conds.append(AuditLogModel.occurred_at <= end_at)
        if keyword:
            kw = f"%{keyword}%"
            conds.append(
                (AuditLogModel.username.like(kw))
                | (AuditLogModel.path.like(kw))
                | (AuditLogModel.resource_id.like(kw))
            )

        where = and_(*conds) if conds else None

        total_stmt = select(func.count(AuditLogModel.id))
        if where is not None:
            total_stmt = total_stmt.where(where)
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = select(AuditLogModel)
        if where is not None:
            stmt = stmt.where(where)
        stmt = stmt.order_by(AuditLogModel.occurred_at.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_domain(r) for r in rows], int(total)

    @staticmethod
    def _to_domain(row: AuditLogModel) -> AuditLog:
        return AuditLog(
            id=row.id,
            occurred_at=row.occurred_at,
            user_id=row.user_id,
            username=row.username,
            method=row.method,
            path=row.path,
            resource=row.resource,
            resource_id=row.resource_id,
            action=row.action,
            status_code=row.status_code,
            ip=row.ip,
            user_agent=row.user_agent,
            request_id=row.request_id,
            detail=row.detail,
        )

"""规则仓储（Admin 端，包含版本管理）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fangyu_shared.schemas.disposition import Disposition, allow
from fangyu_shared.schemas.rule import (
    DecisionRule,
    RuleCondition,
    RuleKind,
    RulePriority,
    RuleStatus,
    ScoringRule,
)

from src.domain.rule.version import RuleVersion
from src.infrastructure.repositories.models import RuleModel, RuleVersionModel

AnyRule = DecisionRule | ScoringRule


def _dump_disposition(rule: AnyRule) -> dict | None:
    """打分规则无处置，落库为 NULL。"""
    if isinstance(rule, DecisionRule):
        return rule.disposition.model_dump(by_alias=True, mode="json")
    return None


class RuleAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, rule_id: int) -> AnyRule | None:
        row = await self._session.get(RuleModel, rule_id)
        return self._to_domain(row) if row else None

    async def list_by_app(
        self,
        app_id: int,
        *,
        status: RuleStatus | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AnyRule], int]:
        base = select(RuleModel).where(RuleModel.app_id == app_id)
        if status is not None:
            base = base.where(RuleModel.status == status.value)
        if keyword:
            base = base.where(RuleModel.name.ilike(f"%{keyword}%"))

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(RuleModel.updated_at.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()

        return [self._to_domain(r) for r in rows if r is not None], int(total)

    async def create(self, rule: AnyRule) -> AnyRule:
        model = RuleModel(
            app_id=rule.app_id,
            name=rule.name,
            description=rule.description or "",
            status=rule.status.value,
            priority=rule.priority.value,
            kind=rule.kind.value,
            weight=getattr(rule, "weight", 0),
            disposition=_dump_disposition(rule),
            conditions=[c.model_dump(mode="json") for c in rule.conditions],
            match_all=rule.match_all,
            rule_group=rule.group,
            tags=list(rule.tags),
            version=rule.version,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def update(self, rule: AnyRule) -> AnyRule:
        assert rule.id is not None
        model = await self._session.get(RuleModel, rule.id)
        if model is None:
            raise LookupError(f"rule {rule.id} not found")
        model.name = rule.name
        model.description = rule.description or ""
        model.status = rule.status.value
        model.priority = rule.priority.value
        model.kind = rule.kind.value
        model.weight = getattr(rule, "weight", 0)
        model.disposition = _dump_disposition(rule)
        model.conditions = [c.model_dump(mode="json") for c in rule.conditions]
        model.match_all = rule.match_all
        model.rule_group = rule.group
        model.tags = list(rule.tags)
        model.version = rule.version
        if rule.published_at:
            model.published_at = rule.published_at
        await self._session.flush()
        return self._to_domain(model)

    async def update_status(self, rule_id: int, status: RuleStatus) -> AnyRule | None:
        model = await self._session.get(RuleModel, rule_id)
        if model is None:
            return None
        model.status = status.value
        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, rule_id: int) -> bool:
        model = await self._session.get(RuleModel, rule_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def touch_published(self, rule_id: int, at: datetime) -> None:
        model = await self._session.get(RuleModel, rule_id)
        if model is not None:
            model.published_at = at

    # ---------- 版本 ----------
    async def add_version(self, version: RuleVersion) -> RuleVersion:
        model = RuleVersionModel(
            rule_id=version.rule_id,
            version=version.version,
            author_id=version.author_id,
            change_summary=version.change_summary,
            snapshot=version.snapshot,
            published_at=version.published_at,
        )
        self._session.add(model)
        await self._session.flush()
        return RuleVersion(
            id=model.id,
            rule_id=model.rule_id,
            version=model.version,
            snapshot=dict(model.snapshot or {}),
            author_id=model.author_id,
            change_summary=model.change_summary,
            created_at=model.created_at,
            published_at=model.published_at,
        )

    async def list_versions(self, rule_id: int, *, limit: int = 50) -> list[RuleVersion]:
        stmt = (
            select(RuleVersionModel)
            .where(RuleVersionModel.rule_id == rule_id)
            .order_by(RuleVersionModel.version.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            RuleVersion(
                id=r.id,
                rule_id=r.rule_id,
                version=r.version,
                snapshot=dict(r.snapshot or {}),
                author_id=r.author_id,
                change_summary=r.change_summary,
                created_at=r.created_at,
                published_at=r.published_at,
            )
            for r in rows
        ]

    async def get_version(self, rule_id: int, version: int) -> RuleVersion | None:
        stmt = (
            select(RuleVersionModel)
            .where(RuleVersionModel.rule_id == rule_id)
            .where(RuleVersionModel.version == version)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return RuleVersion(
            id=row.id,
            rule_id=row.rule_id,
            version=row.version,
            snapshot=dict(row.snapshot or {}),
            author_id=row.author_id,
            change_summary=row.change_summary,
            created_at=row.created_at,
            published_at=row.published_at,
        )

    @staticmethod
    def _to_domain(row: RuleModel) -> AnyRule:
        common = {
            "id": row.id,
            "appId": row.app_id,
            "name": row.name,
            "description": row.description,
            "status": RuleStatus(row.status),
            "priority": RulePriority(row.priority),
            "conditions": [RuleCondition.model_validate(c) for c in (row.conditions or [])],
            "matchAll": bool(row.match_all),
            "group": row.rule_group,
            "tags": list(row.tags or []),
            "version": row.version,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
            "publishedAt": row.published_at,
        }
        if RuleKind(row.kind) == RuleKind.SCORING:
            return ScoringRule(kind=RuleKind.SCORING, weight=row.weight, **common)
        # 历史行 disposition 可能为空：退化为放行，避免整页规则加载失败
        disposition = (
            Disposition.model_validate(row.disposition) if row.disposition else allow()
        )
        return DecisionRule(kind=RuleKind.DECISION, disposition=disposition, **common)

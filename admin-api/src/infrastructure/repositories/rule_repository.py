"""规则仓储（Admin 端，包含版本管理）。"""

from __future__ import annotations

import json as _json
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fangyu_shared.schemas.disposition import DecisionDisposition, Disposition, Mechanism, allow
from fangyu_shared.schemas.rule import (
    DecisionRule,
    RuleCondition,
    RuleKind,
    RulePriority,
    RuleStatus,
    ScoringRule,
)

from src.domain.rule.version import RuleVersion
from src.infrastructure.repositories.models import RuleModel, RuleSiteModel, RuleVersionModel

AnyRule = DecisionRule | ScoringRule


def _parse_disposition(raw: dict | str | None) -> dict | None:
    """兼容 MySQLJSON 列在部分驱动下返回 str 而非 dict 的问题。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        return _json.loads(raw)
    return raw


def _dump_disposition_match(rule: AnyRule) -> dict | None:
    if isinstance(rule, DecisionRule):
        return rule.disposition_match.model_dump(by_alias=True, mode="json")
    return None


def _dump_disposition_miss(rule: AnyRule) -> dict | None:
    if isinstance(rule, DecisionRule):
        return rule.disposition_miss.model_dump(by_alias=True, mode="json")
    return None


class RuleAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, rule_id: int) -> AnyRule | None:
        row = await self._session.get(RuleModel, rule_id)
        if row is None:
            return None
        site_ids = await self.list_site_ids(rule_id)
        return self._to_domain(row, site_ids=site_ids)

    async def list_site_ids(self, rule_id: int) -> list[int]:
        """查询规则已绑定的站点 id 列表。"""
        stmt = select(RuleSiteModel.site_id).where(RuleSiteModel.rule_id == rule_id)
        rows = (await self._session.execute(stmt)).all()
        return sorted(row[0] for row in rows)

    async def _site_ids_map(self, rule_ids: list[int]) -> dict[int, list[int]]:
        """批量查询多条规则的绑定站点，避免逐条查询的 N+1。"""
        if not rule_ids:
            return {}
        stmt = select(RuleSiteModel.rule_id, RuleSiteModel.site_id).where(
            RuleSiteModel.rule_id.in_(rule_ids)
        )
        rows = (await self._session.execute(stmt)).all()
        mapping: dict[int, list[int]] = {rid: [] for rid in rule_ids}
        for rule_id, site_id in rows:
            mapping.setdefault(rule_id, []).append(site_id)
        for ids in mapping.values():
            ids.sort()
        return mapping

    async def list_all(
        self,
        *,
        status: RuleStatus | None = None,
        keyword: str | None = None,
        site_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AnyRule], int]:
        """规则列表。site_id 不为空时只返回绑定了该站点的规则。"""
        base = select(RuleModel)
        if site_id is not None:
            base = base.where(
                RuleModel.id.in_(
                    select(RuleSiteModel.rule_id).where(RuleSiteModel.site_id == site_id)
                )
            )
        if status is not None:
            base = base.where(RuleModel.status == status.value)
        if keyword:
            base = base.where(RuleModel.name.ilike(f"%{keyword}%"))

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(RuleModel.updated_at.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()

        valid = [r for r in rows if r is not None]
        site_map = await self._site_ids_map([r.id for r in valid])
        return [self._to_domain(r, site_ids=site_map.get(r.id, [])) for r in valid], int(total)

    async def list_by_app(
        self,
        site_id: int,
        *,
        status: RuleStatus | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AnyRule], int]:
        return await self.list_all(
            status=status, keyword=keyword, site_id=site_id, offset=offset, limit=limit
        )

    async def list_published_by_site(self, site_id: int) -> list[AnyRule]:
        """取某站点全部已发布规则，用于同步 Redis 分片。

        返回的规则 app_id 已置为该 site_id，便于直接写入 fangyu:rules:{site_id}。
        """
        stmt = (
            select(RuleModel)
            .where(RuleModel.status == RuleStatus.PUBLISHED.value)
            .where(
                RuleModel.id.in_(
                    select(RuleSiteModel.rule_id).where(RuleSiteModel.site_id == site_id)
                )
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_domain(r, site_ids=[site_id], app_id=site_id) for r in rows if r]

    # ---------- 站点绑定（多对多） ----------
    async def set_sites(self, rule_id: int, site_ids: list[int]) -> list[int]:
        """全量覆盖规则的站点绑定，返回操作前的站点列表（供调用方清理旧分片缓存）。"""
        previous = await self.list_site_ids(rule_id)
        target = sorted(set(site_ids))

        to_remove = [s for s in previous if s not in target]
        to_add = [s for s in target if s not in previous]

        if to_remove:
            await self._session.execute(
                delete(RuleSiteModel)
                .where(RuleSiteModel.rule_id == rule_id)
                .where(RuleSiteModel.site_id.in_(to_remove))
            )
        for site_id in to_add:
            self._session.add(RuleSiteModel(rule_id=rule_id, site_id=site_id))

        await self._session.flush()
        return previous

    async def bind_rules_to_site(self, site_id: int, rule_ids: list[int]) -> list[int]:
        """全量覆盖某站点绑定的规则，返回操作前的规则列表。"""
        stmt = select(RuleSiteModel.rule_id).where(RuleSiteModel.site_id == site_id)
        previous = sorted(row[0] for row in (await self._session.execute(stmt)).all())
        target = sorted(set(rule_ids))

        to_remove = [r for r in previous if r not in target]
        to_add = [r for r in target if r not in previous]

        if to_remove:
            await self._session.execute(
                delete(RuleSiteModel)
                .where(RuleSiteModel.site_id == site_id)
                .where(RuleSiteModel.rule_id.in_(to_remove))
            )
        for rule_id in to_add:
            self._session.add(RuleSiteModel(rule_id=rule_id, site_id=site_id))

        await self._session.flush()
        return previous

    async def count_rules_by_site(self, site_ids: list[int]) -> dict[int, int]:
        """批量统计各站点绑定的规则数，供站点列表展示。"""
        if not site_ids:
            return {}
        stmt = (
            select(RuleSiteModel.site_id, func.count(RuleSiteModel.rule_id))
            .where(RuleSiteModel.site_id.in_(site_ids))
            .group_by(RuleSiteModel.site_id)
        )
        rows = (await self._session.execute(stmt)).all()
        counts = {sid: 0 for sid in site_ids}
        for site_id, count in rows:
            counts[site_id] = int(count)
        return counts

    async def create(self, rule: AnyRule) -> AnyRule:
        model = RuleModel(
            name=rule.name,
            description=rule.description or "",
            status=rule.status.value,
            priority=rule.priority.value,
            kind=rule.kind.value,
            weight=getattr(rule, "weight", 0),
            disposition_match=_dump_disposition_match(rule),
            disposition_miss=_dump_disposition_miss(rule),
            conditions=[c.model_dump(mode="json") for c in rule.conditions],
            match_all=rule.match_all,
            rule_group=rule.group,
            tags=list(rule.tags),
            version=rule.version,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)

        # 创建时若带了 siteIds，一并写入关联表
        if rule.site_ids:
            for site_id in sorted(set(rule.site_ids)):
                self._session.add(RuleSiteModel(rule_id=model.id, site_id=site_id))
            await self._session.flush()

        return self._to_domain(model, site_ids=sorted(set(rule.site_ids)))

    async def update(self, rule: AnyRule) -> AnyRule:
        assert rule.id is not None
        model = await self._session.get(RuleModel, rule.id)
        if model is None:
            raise LookupError(f"rule {rule.id} not found")
        site_ids = await self.list_site_ids(rule.id)
        model.name = rule.name
        model.description = rule.description or ""
        model.status = rule.status.value
        model.priority = rule.priority.value
        model.kind = rule.kind.value
        model.weight = getattr(rule, "weight", 0)
        model.disposition_match = _dump_disposition_match(rule)
        model.disposition_miss = _dump_disposition_miss(rule)
        model.conditions = [c.model_dump(mode="json") for c in rule.conditions]
        model.match_all = rule.match_all
        model.rule_group = rule.group
        model.tags = list(rule.tags)
        model.version = rule.version
        if rule.published_at:
            model.published_at = rule.published_at
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model, site_ids=site_ids)

    async def update_status(self, rule_id: int, status: RuleStatus) -> AnyRule | None:
        model = await self._session.get(RuleModel, rule_id)
        if model is None:
            return None
        site_ids = await self.list_site_ids(rule_id)
        model.status = status.value
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model, site_ids=site_ids)

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
        await self._session.refresh(model)
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

    async def list_app_ids_with_published_rules(self) -> list[int]:
        """返回绑定了已发布规则的所有 site_id，供 scheduler 全量同步缓存使用。"""
        stmt = (
            select(RuleSiteModel.site_id)
            .join(RuleModel, RuleModel.id == RuleSiteModel.rule_id)
            .where(RuleModel.status == RuleStatus.PUBLISHED.value)
            .distinct()
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    @staticmethod
    def _to_domain(
        row: RuleModel,
        *,
        site_ids: list[int] | None = None,
        app_id: int = 0,
    ) -> AnyRule:
        """把 ORM 行转为领域对象。

        app_id 是「写入哪个站点的 Redis 分片」的标记，只有同步缓存时才需要指定；
        admin 侧查询一律传 0（规则不归属单一站点）。
        """
        common = {
            "id": row.id,
            "appId": app_id,
            "siteIds": list(site_ids or []),
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
        kind = RuleKind(row.kind) if row.kind else RuleKind.DECISION
        if kind == RuleKind.SCORING:
            return ScoringRule(kind=RuleKind.SCORING, weight=row.weight or 0, **common)
        # disposition_match/miss 可能为 str（部分 MySQL 驱动）或 dict，统一解析
        _pass = DecisionDisposition(mechanism=Mechanism.PASS)
        parsed_match = _parse_disposition(row.disposition_match)
        disposition_match = (
            DecisionDisposition.model_validate(parsed_match)
            if parsed_match
            else _pass
        )
        parsed_miss = _parse_disposition(row.disposition_miss)
        disposition_miss = (
            DecisionDisposition.model_validate(parsed_miss)
            if parsed_miss
            else _pass
        )
        return DecisionRule(
            kind=RuleKind.DECISION,
            disposition_match=disposition_match,
            disposition_miss=disposition_miss,
            **common,
        )

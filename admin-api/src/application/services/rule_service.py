"""规则管理服务。"""

from __future__ import annotations

from datetime import datetime

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
)
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.rule import DecisionRule, RuleKind, RuleStatus, ScoringRule

from src.domain.rule.state_machine import RuleStateMachine
from src.domain.rule.version import RuleVersion
from src.infrastructure.cache.rule_cache import RuleCache
from src.infrastructure.repositories.rule_repository import AnyRule, RuleAdminRepository

_logger = get_logger("admin.rule_service")


def _rule_from_snapshot(snapshot: dict) -> AnyRule:
    """按 kind 还原规则快照。历史快照缺 kind 时按决策规则处理。"""
    kind = str(snapshot.get("kind") or RuleKind.DECISION.value)
    if kind == RuleKind.SCORING.value:
        return ScoringRule.model_validate(snapshot)
    return DecisionRule.model_validate(snapshot)


class RuleService:
    def __init__(
        self,
        *,
        rule_repo: RuleAdminRepository,
        rule_cache: RuleCache,
    ) -> None:
        self._repo = rule_repo
        self._cache = rule_cache

    async def list_by_app(
        self,
        app_id: int,
        *,
        status: RuleStatus | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AnyRule], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_by_app(
            app_id,
            status=status,
            keyword=keyword,
            offset=offset,
            limit=page_size,
        )

    async def get(self, rule_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        return rule

    async def create(self, rule: AnyRule, author_id: int) -> AnyRule:
        rule.status = RuleStatus.DRAFT
        rule.version = 1
        created = await self._repo.create(rule)
        assert created.id is not None
        await self._repo.add_version(
            RuleVersion(
                id=None,
                rule_id=created.id,
                version=1,
                snapshot=created.model_dump(by_alias=True, mode="json"),
                author_id=author_id,
                change_summary="创建规则",
            )
        )
        _logger.info("rule_created", rule_id=created.id, app_id=created.app_id)
        return created

    async def update(self, rule_id: int, patch: AnyRule, author_id: int) -> AnyRule:
        current = await self._repo.get(rule_id)
        if current is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        if current.status == RuleStatus.ARCHIVED:
            raise BusinessRuleException("已归档的规则不可修改")

        if patch.kind != current.kind:
            raise BusinessRuleException("不支持变更规则种类，请新建规则")

        current.name = patch.name or current.name
        current.description = (
            patch.description if patch.description is not None else current.description
        )
        current.priority = patch.priority
        current.conditions = patch.conditions
        current.match_all = patch.match_all
        current.group = patch.group
        current.tags = list(patch.tags)
        # weight / disposition 按种类互斥，只拷贝该种类实际持有的那个
        if isinstance(current, ScoringRule) and isinstance(patch, ScoringRule):
            current.weight = patch.weight
        elif isinstance(current, DecisionRule) and isinstance(patch, DecisionRule):
            current.disposition = patch.disposition
        current.version += 1
        current.status = RuleStatus.DRAFT

        updated = await self._repo.update(current)
        await self._repo.add_version(
            RuleVersion(
                id=None,
                rule_id=rule_id,
                version=updated.version,
                snapshot=updated.model_dump(by_alias=True, mode="json"),
                author_id=author_id,
                change_summary="编辑规则",
            )
        )
        await self._cache.remove(updated.app_id, rule_id)
        _logger.info("rule_updated", rule_id=rule_id, version=updated.version)
        return updated

    async def publish(self, rule_id: int, author_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        RuleStateMachine.ensure_transition(rule.status, RuleStatus.PUBLISHED)
        rule.status = RuleStatus.PUBLISHED
        now = datetime.utcnow()
        rule.published_at = now
        rule.version += 1
        updated = await self._repo.update(rule)
        await self._repo.touch_published(rule_id, now)
        await self._repo.add_version(
            RuleVersion(
                id=None,
                rule_id=rule_id,
                version=updated.version,
                snapshot=updated.model_dump(by_alias=True, mode="json"),
                author_id=author_id,
                change_summary="发布",
                published_at=now,
            )
        )
        await self._cache.upsert(updated)
        _logger.info("rule_published", rule_id=rule_id, version=updated.version)
        return updated

    async def disable(self, rule_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        RuleStateMachine.ensure_transition(rule.status, RuleStatus.DISABLED)
        updated = await self._repo.update_status(rule_id, RuleStatus.DISABLED)
        if updated is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        await self._cache.remove(updated.app_id, rule_id)
        _logger.info("rule_disabled", rule_id=rule_id)
        return updated

    async def archive(self, rule_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        RuleStateMachine.ensure_transition(rule.status, RuleStatus.ARCHIVED)
        updated = await self._repo.update_status(rule_id, RuleStatus.ARCHIVED)
        if updated is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        await self._cache.remove(updated.app_id, rule_id)
        _logger.info("rule_archived", rule_id=rule_id)
        return updated

    async def delete(self, rule_id: int) -> None:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        if rule.status == RuleStatus.PUBLISHED:
            raise BusinessRuleException("已发布规则请先禁用/归档再删除")
        await self._repo.delete(rule_id)
        await self._cache.remove(rule.app_id, rule_id)
        _logger.info("rule_deleted", rule_id=rule_id)

    async def list_versions(self, rule_id: int) -> list[RuleVersion]:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        return await self._repo.list_versions(rule_id)

    async def rollback(self, rule_id: int, target_version: int, author_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        snap = await self._repo.get_version(rule_id, target_version)
        if snap is None:
            raise ResourceNotFoundException(
                f"版本不存在: rule={rule_id} version={target_version}"
            )
        target_rule = _rule_from_snapshot(snap.snapshot)
        target_rule.id = rule_id
        target_rule.status = RuleStatus.DRAFT
        target_rule.version = rule.version + 1
        target_rule.published_at = None
        updated = await self._repo.update(target_rule)
        await self._repo.add_version(
            RuleVersion(
                id=None,
                rule_id=rule_id,
                version=updated.version,
                snapshot=updated.model_dump(by_alias=True, mode="json"),
                author_id=author_id,
                change_summary=f"回滚到版本 {target_version}",
            )
        )
        await self._cache.remove(updated.app_id, rule_id)
        _logger.info("rule_rollback", rule_id=rule_id, target=target_version)
        return updated

    async def sync_published_to_cache(self, app_id: int) -> int:
        rules, _ = await self._repo.list_by_app(
            app_id, status=RuleStatus.PUBLISHED, limit=9999
        )
        await self._cache.sync_app_rules(app_id, rules)
        _logger.info("rule_cache_synced", app_id=app_id, count=len(rules))
        return len(rules)

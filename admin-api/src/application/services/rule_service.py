"""规则管理服务。"""

from __future__ import annotations

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
)
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.rule import DecisionRule, RuleKind, RuleStatus, ScoringRule
from fangyu_shared.utils.time import local_now

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

    async def list_all(
        self,
        *,
        status: RuleStatus | None = None,
        keyword: str | None = None,
        site_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AnyRule], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_all(
            status=status, keyword=keyword, site_id=site_id, offset=offset, limit=page_size
        )

    async def set_sites(self, rule_id: int, site_ids: list[int]) -> AnyRule:
        """全量覆盖一条规则绑定的站点，并同步受影响站点的缓存分片。"""
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")

        previous = await self._repo.set_sites(rule_id, site_ids)
        target = sorted(set(site_ids))

        # 已发布规则才需要动缓存：解绑的站点要移除，新绑的站点要写入
        if rule.status == RuleStatus.PUBLISHED:
            removed = [s for s in previous if s not in target]
            if removed:
                await self._cache.remove_from_sites(rule_id, removed)
            added = [s for s in target if s not in previous]
            if added:
                await self._cache.upsert_to_sites(rule, added)

        updated = await self._repo.get(rule_id)
        assert updated is not None
        _logger.info("rule_sites_set", rule_id=rule_id, site_count=len(target))
        return updated

    async def bind_rules_to_site(self, site_id: int, rule_ids: list[int]) -> int:
        """全量覆盖某站点绑定的规则，并重建该站点的缓存分片。

        返回绑定后的规则条数。
        """
        await self._repo.bind_rules_to_site(site_id, rule_ids)
        # 绑定关系变了，整片重建最稳妥（避免逐条增删漏掉已下线规则）
        await self.sync_published_to_cache(site_id)
        _logger.info("site_rules_bound", site_id=site_id, rule_count=len(set(rule_ids)))
        return len(set(rule_ids))

    async def count_rules_by_site(self, site_ids: list[int]) -> dict[int, int]:
        return await self._repo.count_rules_by_site(site_ids)

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

    async def create(self, rule: AnyRule, author_id: int, *, site_ids: list[int] | None = None) -> AnyRule:
        rule.status = RuleStatus.DRAFT
        rule.version = 1
        created = await self._repo.create(rule)
        assert created.id is not None
        if site_ids:
            await self._repo.set_sites(created.id, site_ids)
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
            current.disposition_match = patch.disposition_match
            current.disposition_miss = patch.disposition_miss
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
        # 编辑会把状态打回 draft，需从所有绑定站点的分片移除，等重新发布
        await self._cache.remove_from_sites(rule_id, updated.site_ids)
        _logger.info("rule_updated", rule_id=rule_id, version=updated.version)
        return updated

    async def publish(self, rule_id: int, author_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        RuleStateMachine.ensure_transition(rule.status, RuleStatus.PUBLISHED)
        rule.status = RuleStatus.PUBLISHED
        now = local_now()
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
        # 写入所有绑定站点的分片；未绑定站点的规则发布后不影响任何流量
        await self._cache.upsert_to_sites(updated, updated.site_ids)
        _logger.info(
            "rule_published",
            rule_id=rule_id,
            version=updated.version,
            site_count=len(updated.site_ids),
        )
        return updated

    async def disable(self, rule_id: int) -> AnyRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        RuleStateMachine.ensure_transition(rule.status, RuleStatus.DISABLED)
        updated = await self._repo.update_status(rule_id, RuleStatus.DISABLED)
        if updated is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        await self._cache.remove_from_sites(rule_id, updated.site_ids)
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
        await self._cache.remove_from_sites(rule_id, updated.site_ids)
        _logger.info("rule_archived", rule_id=rule_id)
        return updated

    async def unarchive(self, rule_id: int) -> AnyRule:
        """归档规则恢复为草稿，之后可重新编辑发布。"""
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        RuleStateMachine.ensure_transition(rule.status, RuleStatus.DRAFT)
        updated = await self._repo.update_status(rule_id, RuleStatus.DRAFT)
        if updated is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        _logger.info("rule_unarchived", rule_id=rule_id)
        return updated

    async def delete(self, rule_id: int) -> None:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise ResourceNotFoundException(f"规则不存在: {rule_id}")
        if rule.status == RuleStatus.PUBLISHED:
            raise BusinessRuleException("已发布规则请先禁用/归档再删除")
        await self._repo.delete(rule_id)
        await self._cache.remove_from_sites(rule_id, rule.site_ids)
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
        # 回滚后状态变 draft，从所有绑定站点分片移除
        await self._cache.remove_from_sites(rule_id, updated.site_ids)
        _logger.info("rule_rollback", rule_id=rule_id, target=target_version)
        return updated

    async def sync_published_to_cache(self, site_id: int) -> int:
        """重建指定站点 Redis 分片（全量替换）。

        用游标分页替代 limit=9999，避免规则超量时静默截断。
        """
        all_rules: list[AnyRule] = []
        page_size = 500
        while True:
            batch, total = await self._repo.list_all(
                status=RuleStatus.PUBLISHED, site_id=site_id,
                offset=len(all_rules), limit=page_size,
            )
            all_rules.extend(batch)
            if len(all_rules) >= total or not batch:
                break
        await self._cache.replace_site(site_id, all_rules)
        _logger.info("rule_cache_synced", site_id=site_id, count=len(all_rules))
        return len(all_rules)

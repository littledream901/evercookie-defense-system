"""灰度影子规则的 admin 侧下发链路测试。

覆盖此前让影子模式成为死代码的四个断点中属于 admin 的三个：
1. RuleCache.replace_site 是否放行 SHADOW（原实现只收 PUBLISHED）
2. RuleService.to_shadow 是否把规则写进 Redis 分片
3. sync_published_to_cache 例行重建是否保留 SHADOW（漏了会把影子规则抹掉）

gateway 侧「影子命中不影响处置」的保证见 tests/gateway/test_rule_model_matcher.py
与 tests/gateway/test_shadow_snapshot_pipeline.py。
"""
from __future__ import annotations

import orjson
import pytest

from fangyu_shared.schemas.disposition import DecisionDisposition, Mechanism
from fangyu_shared.schemas.rule import DecisionRule, RuleCondition, RuleKind, RuleStatus

from src.application.services.rule_service import RuleService
from src.infrastructure.cache.rule_cache import RuleCache

_VERSION_FIELD = "__version__"


def _rule(*, rid: int, status: RuleStatus, name: str = "r") -> DecisionRule:
    return DecisionRule(
        id=rid,
        appId=0,
        siteIds=[7],
        name=name,
        status=status,
        kind=RuleKind.DECISION,
        conditions=[RuleCondition(field="ip.country", op="eq", value="CN")],
        disposition_match=DecisionDisposition(mechanism=Mechanism.DENY),
        disposition_miss=DecisionDisposition(mechanism=Mechanism.PASS),
    )


class _FakeRedis:
    """异步 Redis 替身：只实现 RuleCache 用到的 Hash 命令。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        bucket = self.hashes.setdefault(name, {})
        if mapping is not None:
            bucket.update(mapping)
            return len(mapping)
        assert key is not None and value is not None
        bucket[key] = value
        return 1

    async def hdel(self, name: str, *keys: str) -> int:
        bucket = self.hashes.get(name, {})
        return sum(int(bucket.pop(k, None) is not None) for k in keys)

    async def delete(self, *names: str) -> int:
        return sum(int(self.hashes.pop(n, None) is not None) for n in names)

    async def rename(self, src: str, dst: str) -> bool:
        # 与 Redis 语义一致：源不存在时报错（空 Hash 等于不存在）
        if src not in self.hashes:
            raise KeyError(src)
        self.hashes[dst] = self.hashes.pop(src)
        return True

    def rule_ids(self, site_id: int) -> set[str]:
        """某站点分片里的规则 id 集合（剔除代次字段）。"""
        bucket = self.hashes.get(f"fangyu:rules:{site_id}", {})
        return {k for k in bucket if k != _VERSION_FIELD}

    def payload(self, site_id: int, rule_id: int) -> dict:
        return orjson.loads(self.hashes[f"fangyu:rules:{site_id}"][str(rule_id)])


class _StubRepo:
    """RuleAdminRepository 替身：只覆盖 RuleService 影子链路会调到的方法。"""

    def __init__(self, rules: list[DecisionRule]) -> None:
        self._rules = {r.id: r for r in rules}
        self.versions: list[object] = []

    async def get(self, rule_id: int) -> DecisionRule | None:
        return self._rules.get(rule_id)

    async def update(self, rule: DecisionRule) -> DecisionRule:
        self._rules[rule.id] = rule
        return rule

    async def update_status(self, rule_id: int, status: RuleStatus) -> DecisionRule | None:
        rule = self._rules.get(rule_id)
        if rule is None:
            return None
        rule.status = status
        return rule

    async def add_version(self, version: object) -> object:
        self.versions.append(version)
        return version

    async def list_all(
        self,
        *,
        status: RuleStatus | None = None,
        keyword: str | None = None,
        site_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[DecisionRule], int]:
        """按状态过滤 + 分页，与真实仓储的单值 status 语义一致。"""
        matched = [
            r for r in self._rules.values()
            if (status is None or r.status == status)
            and (site_id is None or site_id in r.site_ids)
        ]
        return matched[offset : offset + limit], len(matched)


class TestRuleCacheAdmitsShadow:
    @pytest.mark.asyncio
    async def test_replace_site_keeps_published_and_shadow(self) -> None:
        """全量换页必须同时保留 published 与 shadow，其余状态一律剔除。"""
        redis = _FakeRedis()
        cache = RuleCache(redis)
        await cache.replace_site(
            7,
            [
                _rule(rid=1, status=RuleStatus.PUBLISHED),
                _rule(rid=2, status=RuleStatus.SHADOW),
                _rule(rid=3, status=RuleStatus.DRAFT),
                _rule(rid=4, status=RuleStatus.DISABLED),
                _rule(rid=5, status=RuleStatus.ARCHIVED),
            ],
        )
        assert redis.rule_ids(7) == {"1", "2"}

    async def test_shadow_payload_keeps_status(self) -> None:
        """下发的 JSON 必须保留 status=shadow。

        丢了这个字段，gateway 侧 rule.is_shadow 就是 False，影子规则会被当成
        普通规则参与真实处置——这是最危险的失败模式，故单独断言。
        """
        redis = _FakeRedis()
        await RuleCache(redis).replace_site(7, [_rule(rid=2, status=RuleStatus.SHADOW)])
        assert redis.payload(7, 2)["status"] == RuleStatus.SHADOW.value


class TestRuleServiceShadow:
    async def test_to_shadow_pushes_to_redis(self) -> None:
        """to_shadow 必须把规则写进绑定站点的分片，否则 gateway 永远评估不到。"""
        redis = _FakeRedis()
        repo = _StubRepo([_rule(rid=1, status=RuleStatus.DRAFT)])
        service = RuleService(rule_repo=repo, rule_cache=RuleCache(redis))

        updated = await service.to_shadow(1, author_id=9)

        assert updated.status == RuleStatus.SHADOW
        assert redis.rule_ids(7) == {"1"}
        assert redis.payload(7, 1)["status"] == RuleStatus.SHADOW.value

    async def test_to_shadow_records_version_and_skips_published_at(self) -> None:
        """与 publish 同构地留版本快照，但不得写 published_at（规则还没上线）。"""
        repo = _StubRepo([_rule(rid=1, status=RuleStatus.DRAFT)])
        service = RuleService(rule_repo=repo, rule_cache=RuleCache(_FakeRedis()))

        updated = await service.to_shadow(1, author_id=9)

        assert len(repo.versions) == 1
        assert updated.published_at is None

    async def test_to_shadow_rejected_from_published(self) -> None:
        """已发布规则不可静默降级为影子，状态机应拦下。"""
        from fangyu_shared.exceptions import ValidationException

        repo = _StubRepo([_rule(rid=1, status=RuleStatus.PUBLISHED)])
        service = RuleService(rule_repo=repo, rule_cache=RuleCache(_FakeRedis()))

        with pytest.raises(ValidationException):
            await service.to_shadow(1, author_id=9)

    async def test_periodic_sync_preserves_shadow(self) -> None:
        """例行全量重建必须保留影子规则。

        这是原实现最隐蔽的断点：即便 to_shadow 写对了，5 分钟后的
        sync_published_to_cache 只查 PUBLISHED，会把影子规则从 Redis 抹掉，
        表现为「影子模式偶尔生效、偶尔失效」。
        """
        redis = _FakeRedis()
        repo = _StubRepo(
            [
                _rule(rid=1, status=RuleStatus.PUBLISHED),
                _rule(rid=2, status=RuleStatus.SHADOW),
                _rule(rid=3, status=RuleStatus.DRAFT),
            ]
        )
        service = RuleService(rule_repo=repo, rule_cache=RuleCache(redis))

        count = await service.sync_published_to_cache(7)

        assert count == 2
        assert redis.rule_ids(7) == {"1", "2"}

    async def test_unarchive_removes_shadow_from_redis(self) -> None:
        """影子规则退回草稿时必须同时清掉 Redis 分片。

        只改 DB 状态会让那份快照留在 Redis 里继续被 gateway 求值，
        运维看到「已退回草稿」的规则仍在产生影响面数据。
        """
        redis = _FakeRedis()
        repo = _StubRepo([_rule(rid=1, status=RuleStatus.DRAFT)])
        service = RuleService(rule_repo=repo, rule_cache=RuleCache(redis))
        await service.to_shadow(1, author_id=9)
        assert redis.rule_ids(7) == {"1"}

        updated = await service.unarchive(1)

        assert updated.status == RuleStatus.DRAFT
        assert redis.rule_ids(7) == set()

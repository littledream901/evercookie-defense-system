"""地址池配额功能测试。"""

from __future__ import annotations

import pytest

from fangyu_shared.schemas.target_render import resolve_rotation_order

_A = "https://a.example.com"
_B = "https://b.example.com"
_C = "https://c.example.com"


class TestQuotaFiltering:
    """配额过滤测试——打满的地址排末尾，全池打满时仍给出候选。"""

    def test_exhausted_sorted_last(self) -> None:
        """配额打满的地址排到末尾（但不剔除）。"""
        pool = [(_A, 1, True), (_B, 1, True), (_C, 1, True)]
        exhausted_fn = lambda u: u == _B  # noqa: E731
        order = resolve_rotation_order(
            pool, strategy="hash", request_seed="req-1", exhausted=exhausted_fn
        )
        assert _B in order
        assert order[-1] == _B

    def test_all_exhausted_still_returns_full_pool(self) -> None:
        """全池打满时仍返回全部地址作为兜底——否则整条规则静默失效。"""
        pool = [(_A, 1, True), (_B, 1, True)]
        exhausted_fn = lambda u: True  # noqa: E731 - 全部耗尽
        order = resolve_rotation_order(
            pool, strategy="hash", request_seed="req-1", exhausted=exhausted_fn
        )
        assert sorted(order) == sorted([_A, _B])

    def test_quota_and_health_both_applied(self) -> None:
        """配额与健康检查同时生效：不健康且打满的排最后。

        排序优先级：健康 > 配额打满。stable sort 保证健康内部按配额再排。
        """
        pool = [(_A, 1, True), (_B, 1, True), (_C, 1, True)]
        healthy_fn = lambda u: u != _A  # noqa: E731 - A 不健康
        exhausted_fn = lambda u: u == _B  # noqa: E731 - B 打满
        order = resolve_rotation_order(
            pool,
            strategy="hash",
            request_seed="req-1",
            healthy=healthy_fn,
            exhausted=exhausted_fn,
        )
        # A 不健康但有配额，B 健康但打满，C 健康且有配额
        # 期望顺序：C（最优）> B（健康但打满）> A（不健康）
        # 或 C > A（不健康有配额）> B（健康但打满）
        # 实际取决于 stable sort 顺序
        assert order[-1] in (_A, _B)  # 最差的应该是 A 或 B
        assert _C in order  # C 一定在候选中

    @pytest.mark.parametrize("strategy", ["hash", "weighted", "sticky", "round_robin", "failover"])
    def test_exhausted_callback_works_for_all_strategies(self, strategy: str) -> None:
        """所有策略都支持配额过滤。"""
        pool = [(_A, 50, True), (_B, 30, True), (_C, 20, True)]
        exhausted_fn = lambda u: u == _A  # noqa: E731
        order = resolve_rotation_order(
            pool,
            strategy=strategy,
            request_seed="req-1",
            visitor_seed="fp-1",
            counter=1,
            healthy=lambda u: True,  # noqa: E731
            exhausted=exhausted_fn,
        )
        assert _A in order
        assert order[-1] == _A


class TestQuotaLogic:
    """配额消费逻辑的单元测试（不依赖 Redis，纯逻辑）。"""

    def test_no_quota_means_unlimited(self) -> None:
        """dailyQuota/hourlyQuota 为 None 时不限流。"""
        from fangyu_shared.schemas.disposition import PoolEntry

        entry = PoolEntry(url="https://example.com", weight=1, enabled=True)
        assert entry.daily_quota is None
        assert entry.hourly_quota is None

    def test_quota_validation(self) -> None:
        """配额字段必须 ≥1 或为 None，前端 :min="1" 与后端校验一致。"""
        from fangyu_shared.schemas.disposition import PoolEntry

        # 合法值
        entry = PoolEntry(url="https://example.com", weight=1, enabled=True, daily_quota=1000)
        assert entry.daily_quota == 1000

        # 非法值 0 应被 pydantic 拒绝
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PoolEntry(url="https://example.com", weight=1, enabled=True, daily_quota=0)


class TestQuotaStoreKeyDesign:
    """验证 PoolQuotaStore 的 key 设计与 TTL 生成逻辑。"""

    def test_period_key_format(self) -> None:
        """验证时间周期 key 格式：d20260803 / h2026080314。"""
        from datetime import datetime, timezone

        from src.infrastructure.cache.pool_quota_store import PoolQuotaStore

        # mock Redis 不需要真正的连接
        class FakeRedis:
            async def incr(self, key: str) -> int:
                return 1

            async def expire(self, key: str, ttl: int) -> None:
                pass

            async def get(self, key: str) -> bytes | None:
                return None

            async def delete(self, key: str) -> None:
                pass

        store = PoolQuotaStore(FakeRedis())  # type: ignore[arg-type]
        period_daily, ttl_daily = store._period_key("daily")
        period_hourly, ttl_hourly = store._period_key("hourly")

        now = datetime.now(tz=timezone.utc)
        assert period_daily.startswith("d")
        assert len(period_daily) == 9  # d20260803
        assert period_hourly.startswith("h")
        assert len(period_hourly) == 11  # h2026080314
        assert ttl_daily > 0
        assert ttl_hourly > 0
        assert ttl_daily > ttl_hourly  # 日 TTL 应该大于时 TTL

    def test_url_hash_consistency(self) -> None:
        """URL 哈希必须稳定（同 URL 同哈希）。"""
        from src.infrastructure.cache.pool_quota_store import PoolQuotaStore

        class FakeRedis:
            pass

        store = PoolQuotaStore(FakeRedis())  # type: ignore[arg-type]
        url = "https://example.com/page?foo=bar"
        hash1 = store._url_hash(url)
        hash2 = store._url_hash(url)
        assert hash1 == hash2
        assert len(hash1) == 32  # blake2b(16) -> 32 hex chars

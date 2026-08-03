"""轮询选址策略测试。

覆盖 5 种策略各自的核心性质，以及三条容易在实现里丢掉的共性约束：
1. 稳定性——同一输入必须恒定，否则多副本网关行为不一致
2. 禁用/零权重条目必须被排除
3. 全池不健康时仍要给出候选，不能返回空（否则整条规则静默失效）
"""

from __future__ import annotations

import pytest
from fangyu_shared.schemas.target_render import (
    pick_by_index,
    pick_weighted,
    resolve_rotation_order,
)

_A = "https://a.example.com"
_B = "https://b.example.com"
_C = "https://c.example.com"

# (url, weight, enabled)
_POOL: list[tuple[str, int, bool]] = [(_A, 50, True), (_B, 30, True), (_C, 20, True)]


class TestPickWeighted:
    """权重选址：把权重摊成数轴用哈希落点。"""

    def test_single_entry(self) -> None:
        assert pick_weighted([(_A, 1)], seed="x") == _A

    def test_zero_weight_excluded(self) -> None:
        """权重 0 等于临时禁用，不该被选中。"""
        assert pick_weighted([(_A, 0), (_B, 5)], seed="x") == _B

    def test_all_zero_weight_returns_none(self) -> None:
        assert pick_weighted([(_A, 0), (_B, 0)], seed="x") is None

    def test_deterministic(self) -> None:
        first = pick_weighted([(_A, 50), (_B, 50)], seed="req-1")
        for _ in range(20):
            assert pick_weighted([(_A, 50), (_B, 50)], seed="req-1") == first

    def test_distribution_follows_weight(self) -> None:
        """权重 90:10 时 A 的命中率应显著高于 B。

        断言用宽区间：这是哈希分布而非精确配额，逐次不保证比例，
        大样本下才收敛。区间取 [80%, 98%] 足以证明权重生效又不脆弱。
        """
        hits = [pick_weighted([(_A, 90), (_B, 10)], seed=f"req-{i}") for i in range(2000)]
        a_ratio = hits.count(_A) / len(hits)
        assert 0.80 < a_ratio < 0.98, f"A 命中率 {a_ratio:.2%} 偏离权重 90%"


class TestPickByIndex:
    """下标取址：计数器单调递增，取模在函数内完成。"""

    def test_wraps_around(self) -> None:
        pool = [_A, _B, _C]
        assert pick_by_index(pool, 0) == _A
        assert pick_by_index(pool, 1) == _B
        assert pick_by_index(pool, 2) == _C
        assert pick_by_index(pool, 3) == _A  # 回绕

    def test_large_counter(self) -> None:
        """计数器长期递增不会越界。"""
        assert pick_by_index([_A, _B], 1_000_001) == _B

    def test_empty_pool(self) -> None:
        assert pick_by_index([], 5) is None


class TestHashStrategy:
    def test_deterministic(self) -> None:
        first = resolve_rotation_order(_POOL, strategy="hash", request_seed="req-1")
        for _ in range(20):
            assert (
                resolve_rotation_order(_POOL, strategy="hash", request_seed="req-1") == first
            )

    def test_spreads_across_requests(self) -> None:
        """不同请求应落到不同首选地址，否则失去分摊意义。"""
        firsts = {
            resolve_rotation_order(_POOL, strategy="hash", request_seed=f"req-{i}")[0]
            for i in range(100)
        }
        assert len(firsts) >= 2

    def test_unknown_strategy_falls_back_to_hash(self) -> None:
        """未知策略退化为 hash，而非抛错或返回空。

        新增策略时旧版网关会遇到不认识的值，静默降级比整条规则失效好。
        """
        expected = resolve_rotation_order(_POOL, strategy="hash", request_seed="req-1")
        assert (
            resolve_rotation_order(_POOL, strategy="does_not_exist", request_seed="req-1")
            == expected
        )


class TestStickyStrategy:
    def test_same_visitor_same_target(self) -> None:
        """同一访客恒定落到同一地址——这是 sticky 的全部意义。"""
        order = resolve_rotation_order(
            _POOL, strategy="sticky", request_seed="req-1", visitor_seed="fp-alice"
        )
        for i in range(20):
            again = resolve_rotation_order(
                _POOL, strategy="sticky", request_seed=f"req-{i}", visitor_seed="fp-alice"
            )
            assert again[0] == order[0]

    def test_different_visitors_spread(self) -> None:
        firsts = {
            resolve_rotation_order(
                _POOL, strategy="sticky", request_seed="req-1", visitor_seed=f"fp-{i}"
            )[0]
            for i in range(100)
        }
        assert len(firsts) >= 2

    def test_falls_back_to_request_seed(self) -> None:
        """无 fingerprint（如服务端流量）时退化为按请求分摊。"""
        order = resolve_rotation_order(
            _POOL, strategy="sticky", request_seed="req-1", visitor_seed=""
        )
        assert order[0] in (_A, _B, _C)


class TestRoundRobinStrategy:
    def test_sequential(self) -> None:
        """计数器递增时严格轮转。"""
        picks = [
            resolve_rotation_order(
                _POOL, strategy="round_robin", request_seed="req", counter=i
            )[0]
            for i in range(6)
        ]
        assert picks == [_A, _B, _C, _A, _B, _C]

    def test_without_counter_falls_back_to_hash(self) -> None:
        """计数器不可用（Redis 故障）时退化为 hash，不让决策失败。"""
        expected = resolve_rotation_order(_POOL, strategy="hash", request_seed="req-1")
        assert (
            resolve_rotation_order(
                _POOL, strategy="round_robin", request_seed="req-1", counter=None
            )
            == expected
        )


class TestFailoverStrategy:
    def test_prefers_first_when_healthy(self) -> None:
        order = resolve_rotation_order(
            _POOL, strategy="failover", request_seed="req", healthy=lambda u: True
        )
        assert order[0] == _A

    def test_skips_unhealthy_primary(self) -> None:
        order = resolve_rotation_order(
            _POOL, strategy="failover", request_seed="req", healthy=lambda u: u != _A
        )
        assert order[0] == _B

    def test_unhealthy_sorted_last_not_dropped(self) -> None:
        """不健康的地址排到末尾而非剔除——探测数据可能是错的，留作兜底。"""
        order = resolve_rotation_order(
            _POOL, strategy="failover", request_seed="req", healthy=lambda u: u != _A
        )
        assert _A in order
        assert order[-1] == _A

    def test_all_unhealthy_still_returns_candidates(self) -> None:
        """全池不健康时仍给出候选，否则整条规则静默失效。"""
        order = resolve_rotation_order(
            _POOL, strategy="failover", request_seed="req", healthy=lambda u: False
        )
        assert len(order) == 3

    def test_health_applies_to_other_strategies(self) -> None:
        """健康排序对所有策略生效，不只是 failover。"""
        order = resolve_rotation_order(
            _POOL, strategy="hash", request_seed="req-1", healthy=lambda u: u == _C
        )
        assert order[0] == _C


class TestPoolFiltering:
    """共性约束：条目过滤。"""

    def test_disabled_excluded(self) -> None:
        pool = [(_A, 10, False), (_B, 10, True)]
        for strategy in ("hash", "weighted", "sticky", "round_robin", "failover"):
            order = resolve_rotation_order(
                pool, strategy=strategy, request_seed="req", counter=0, healthy=lambda u: True
            )
            assert _A not in order, f"{strategy} 未排除禁用条目"
            assert order == [_B]

    def test_zero_weight_excluded(self) -> None:
        pool = [(_A, 0, True), (_B, 10, True)]
        order = resolve_rotation_order(pool, strategy="hash", request_seed="req")
        assert order == [_B]

    def test_blank_url_excluded(self) -> None:
        pool = [("   ", 10, True), (_B, 10, True)]
        order = resolve_rotation_order(pool, strategy="hash", request_seed="req")
        assert order == [_B]

    def test_empty_pool_returns_empty(self) -> None:
        assert resolve_rotation_order([], strategy="hash", request_seed="req") == []

    def test_all_disabled_returns_empty(self) -> None:
        pool = [(_A, 10, False), (_B, 10, False)]
        assert resolve_rotation_order(pool, strategy="hash", request_seed="req") == []

    @pytest.mark.parametrize("strategy", ["hash", "weighted", "sticky", "round_robin", "failover"])
    def test_order_is_permutation_of_pool(self, strategy: str) -> None:
        """任何策略都必须返回全部可用地址的排列，不能丢地址。

        丢地址会让 render_pool 的顺延失去候选——首选渲染失败就整条规则失效。
        """
        order = resolve_rotation_order(
            _POOL,
            strategy=strategy,
            request_seed="req-1",
            visitor_seed="fp-1",
            counter=1,
            healthy=lambda u: True,
        )
        assert sorted(order) == sorted([_A, _B, _C])

"""PROF → INTEL 回流单元测试。

这条链路的失效方式是「静默」的：写少了没人发现（情报表只是空着），写多了
会把上万条 /32 灌进 ip_profile，而 gateway 侧每 30 秒要把它们全量载入内存
做 CIDR 匹配。因此阈值、配额、来源标记都必须被钉住。
"""

from __future__ import annotations

import pytest
from fangyu_shared.reputation import IpReputationRow
from src.infrastructure.repositories.intel_repository import IntelType
from src.infrastructure.reputation_intel_feedback import (
    NOTE_PREFIX,
    ReputationIntelFeedback,
    ReputationIntelFeedbackConfig,
)


class _FakeIntelService:
    def __init__(self) -> None:
        self.calls: list[tuple[IntelType, list[dict]]] = []

    async def bulk_import(self, intel_type: IntelType, records: list[dict]) -> dict[str, int]:
        self.calls.append((intel_type, records))
        return {"imported": len(records), "skipped": 0}

    @property
    def records(self) -> list[dict]:
        return self.calls[0][1] if self.calls else []


def _row(ip: str, *, total: int, blocked: int, app_id: int = 1) -> IpReputationRow:
    return IpReputationRow(app_id=app_id, ip=ip, total=total, blocked=blocked)


def _feedback(svc: _FakeIntelService, **kw) -> ReputationIntelFeedback:
    return ReputationIntelFeedback(svc, ReputationIntelFeedbackConfig(**kw))  # type: ignore[arg-type]


# ---------- 阈值 ----------
@pytest.mark.asyncio
async def test_high_risk_ip_written() -> None:
    svc = _FakeIntelService()
    # 300 次里拦了 291 次 → 声誉分 3.0，远低于阈值
    written = await _feedback(svc).write([_row("203.0.113.7", total=300, blocked=291)])

    assert written == 1
    intel_type, records = svc.calls[0]
    assert intel_type is IntelType.ip_profile
    assert records[0]["cidr"] == "203.0.113.7/32"
    assert records[0]["risk_score"] == 97


@pytest.mark.asyncio
async def test_score_above_threshold_skipped() -> None:
    """拦截率不够高的 IP 不该沉淀成长期情报。"""
    svc = _FakeIntelService()
    # 300 次里拦了 90 次 → 70 分，高于默认阈值 20
    written = await _feedback(svc).write([_row("203.0.113.7", total=300, blocked=90)])

    assert written == 0
    assert svc.calls == []


@pytest.mark.asyncio
async def test_low_sample_count_skipped() -> None:
    """样本不足时即使全被拦也不写：情报条目影响所有租户，证据门槛要更高。"""
    svc = _FakeIntelService()
    written = await _feedback(svc).write([_row("203.0.113.7", total=10, blocked=10)])

    assert written == 0
    assert svc.calls == []


@pytest.mark.asyncio
async def test_thresholds_are_configurable() -> None:
    """阈值必须可配，否则调参只能改代码。"""
    svc = _FakeIntelService()
    fb = _feedback(svc, score_threshold=80.0, min_samples=10)
    written = await fb.write([_row("203.0.113.7", total=10, blocked=3)])  # 70 分

    assert written == 1


@pytest.mark.asyncio
async def test_disabled_writes_nothing() -> None:
    svc = _FakeIntelService()
    written = await _feedback(svc, enabled=False).write(
        [_row("203.0.113.7", total=300, blocked=300)]
    )

    assert written == 0
    assert svc.calls == []


# ---------- 写入量控制 ----------
@pytest.mark.asyncio
async def test_entries_capped_per_run() -> None:
    """单次写入必须有上限，否则一次扫描流量能灌进上万行。"""
    svc = _FakeIntelService()
    rows = [_row(f"203.0.113.{i}", total=300, blocked=300) for i in range(1, 60)]

    written = await _feedback(svc, max_entries_per_run=10).write(rows)

    assert written == 10
    assert len(svc.records) == 10


@pytest.mark.asyncio
async def test_cap_keeps_worst_offenders() -> None:
    """被截断时留下的必须是分数最低（最确凿）的那些。"""
    svc = _FakeIntelService()
    rows = [
        _row("203.0.113.1", total=300, blocked=300),  # 0 分
        _row("203.0.113.2", total=300, blocked=280),  # 6.67 分
        _row("203.0.113.3", total=300, blocked=255),  # 15 分
    ]

    await _feedback(svc, max_entries_per_run=2).write(rows)

    cidrs = [r["cidr"] for r in svc.records]
    assert cidrs == ["203.0.113.1/32", "203.0.113.2/32"]


@pytest.mark.asyncio
async def test_same_ip_across_tenants_deduped_to_worst() -> None:
    """情报表按 CIDR 唯一：同一 IP 多租户命中时只留最恶劣的那次观测。"""
    svc = _FakeIntelService()
    rows = [
        _row("203.0.113.7", total=300, blocked=255, app_id=1),  # 15 分
        _row("203.0.113.7", total=300, blocked=300, app_id=2),  # 0 分
    ]

    await _feedback(svc).write(rows)

    assert len(svc.records) == 1
    assert svc.records[0]["risk_score"] == 100
    assert "app=2" in svc.records[0]["note"]


# ---------- 来源标记与字段 ----------
@pytest.mark.asyncio
async def test_source_marked_by_note_prefix() -> None:
    """自动推导的条目必须能与外部拉取 / 人工录入区分开。"""
    svc = _FakeIntelService()
    await _feedback(svc).write([_row("203.0.113.7", total=300, blocked=300)])

    assert svc.records[0]["note"].startswith(f"{NOTE_PREFIX}:")


@pytest.mark.asyncio
async def test_network_type_left_empty() -> None:
    """不能瞎填 network_type。

    行为统计不能推断「这是什么网络」。填 DATACENTER 之类的占位值会在 gateway
    侧覆盖 MMDB 解析出的真实类型，把住宅 IP 说成数据中心并额外加分。
    """
    svc = _FakeIntelService()
    await _feedback(svc).write([_row("203.0.113.7", total=300, blocked=300)])

    rec = svc.records[0]
    assert rec["network_type"] == ""
    assert rec["is_vpn"] is False
    assert rec["is_proxy"] is False
    assert rec["is_tor"] is False


@pytest.mark.asyncio
async def test_ipv6_written_as_128() -> None:
    svc = _FakeIntelService()
    await _feedback(svc).write([_row("2001:db8::1", total=300, blocked=300)])

    assert svc.records[0]["cidr"] == "2001:db8::1/128"


@pytest.mark.asyncio
async def test_malformed_ip_skipped() -> None:
    """MV 里出现脏数据时跳过该行，不能让整批写入失败。"""
    svc = _FakeIntelService()
    rows = [
        _row("not-an-ip", total=300, blocked=300),
        _row("203.0.113.7", total=300, blocked=300),
    ]

    written = await _feedback(svc).write(rows)

    assert written == 1
    assert svc.records[0]["cidr"] == "203.0.113.7/32"


@pytest.mark.asyncio
async def test_empty_input_does_not_touch_db() -> None:
    svc = _FakeIntelService()
    assert await _feedback(svc).write([]) == 0
    assert svc.calls == []

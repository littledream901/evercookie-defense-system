"""声誉回流手动同步服务（admin-api 侧）。

周期执行归 worker（数据面常驻进程，见
``worker/src/application/writers/reputation_writer.py``）。本服务只服务
``POST /threat-intel/sync`` 的手动触发：运营改完阈值想立刻看效果、或 worker
刚故障恢复时，不必等下一个整点。

聚合 SQL 与评分公式复用 :mod:`fangyu_shared.reputation`，与 worker 同一份
实现——否则「手动同步一次」会把周期任务写出的分数改成另一个值，而两侧日志
都显示成功。

手动触发时额外做一件 worker 做不到的事：把高风险 IP 沉淀进情报库
（:class:`ReputationIntelFeedback`，worker 没有 DB 依赖）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fangyu_shared.cache.profile_cache import ProfileCache
from fangyu_shared.clickhouse_manager import ClickHouseClient
from fangyu_shared.reputation import ReputationSyncConfig, ReputationSyncer

from src.infrastructure.reputation_intel_feedback import ReputationIntelFeedback


@dataclass(slots=True)
class ReputationSyncResult:
    ips_written: int = 0
    devices_written: int = 0
    intel_entries_written: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ips_written": self.ips_written,
            "devices_written": self.devices_written,
            "intel_entries_written": self.intel_entries_written,
            "error_count": len(self.errors),
            "errors": self.errors[:20],  # 最多回传 20 条错误摘要，防止响应过大
        }


class ReputationSyncService:
    """从 ClickHouse MV 拉取声誉聚合，写回 Redis ProfileCache 并沉淀情报。"""

    def __init__(
        self,
        *,
        clickhouse: ClickHouseClient,
        profile_cache: ProfileCache,
        lookback_days: int = 7,
        min_samples: int = 5,
        intel_feedback: ReputationIntelFeedback | None = None,
    ) -> None:
        self._syncer = ReputationSyncer(
            clickhouse=clickhouse,
            profile_cache=profile_cache,
            config=ReputationSyncConfig(
                lookback_days=lookback_days,
                min_samples=min_samples,
            ),
            # 复用同一次聚合结果做情报回流，不再为此多扫一遍 MV。
            ip_rows_sink=intel_feedback.write if intel_feedback is not None else None,
        )

    async def sync(self) -> ReputationSyncResult:
        """执行一次完整的声誉同步。fail-open：子步骤相互独立。"""
        outcome = await self._syncer.run_once()
        return ReputationSyncResult(
            ips_written=outcome.ips_written,
            devices_written=outcome.devices_written,
            intel_entries_written=outcome.feedback_written,
            errors=outcome.errors,
        )

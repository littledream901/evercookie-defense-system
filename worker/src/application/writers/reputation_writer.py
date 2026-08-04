"""Reputation 回流周期任务（worker 侧）。

worker 是**周期回流的唯一执行者**：它属于数据面，本就常驻消费 decision_events，
让产出声誉分的进程与产出原始事件的进程同源，避免 admin 重启/多副本时任务重复
执行。admin 侧只保留 ``POST /threat-intel/sync`` 的手动触发。

聚合 SQL 与评分公式都在 :mod:`fangyu_shared.reputation`——两侧共用一份实现，
本类只负责把 worker 的配置翻译过去。
"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.cache.profile_cache import ProfileCache
from fangyu_shared.clickhouse_manager import ClickHouseClient
from fangyu_shared.reputation import (
    ReputationSyncConfig,
    ReputationSyncer,
    calc_score,  # noqa: F401  兼容既有导入方（测试直接引用评分契约）
)
from fangyu_shared.reputation.syncer import ReputationSyncOutcome


@dataclass(slots=True)
class ReputationWriterConfig:
    lookback_days: int = 7
    """向前追溯天数；覆盖更多历史让分数更稳定。"""
    min_samples: int = 5
    """最少样本数门槛；样本不足的 IP/指纹跳过，避免误判。"""
    ip_ttl: int = 86_400
    """IP 画像在 Redis 中的 TTL（秒），默认 24 小时。"""
    device_ttl: int = 86_400
    """设备画像 TTL（秒）。"""


ReputationSyncResult = ReputationSyncOutcome
"""保留旧名字：main.py 与既有测试按这个名字读 ips_written / devices_written。"""


class ReputationWriter:
    """按周期从 ClickHouse 拉取声誉聚合，回写 Redis ProfileCache。"""

    def __init__(
        self,
        *,
        clickhouse: ClickHouseClient,
        profile_cache: ProfileCache,
        config: ReputationWriterConfig | None = None,
    ) -> None:
        cfg = config or ReputationWriterConfig()
        self._syncer = ReputationSyncer(
            clickhouse=clickhouse,
            profile_cache=profile_cache,
            config=ReputationSyncConfig(
                lookback_days=cfg.lookback_days,
                min_samples=cfg.min_samples,
            ),
        )

    async def run_once(self) -> ReputationSyncResult:
        """执行一次完整同步，返回写入统计。"""
        return await self._syncer.run_once()

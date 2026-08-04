"""声誉回流的共享实现（聚合 + 评分 + 写回 ProfileCache）。

为什么放在 shared
-----------------
worker 的周期任务与 admin 的手动触发端点需要**完全相同**的聚合 SQL 与评分
公式。此前两侧各存一份复制粘贴的实现，任何一侧调参都会让「手动同步一次」
把定时任务写出的分数改成另一个值，且两边日志都显示成功——没有任何报警会
指向真正的原因。收口到这里后，两个调用方都只是薄封装。
"""

from __future__ import annotations

from fangyu_shared.reputation.aggregator import (
    DeviceReputationRow,
    IpReputationRow,
    calc_score,
    fetch_device_reputation,
    fetch_ip_reputation,
)
from fangyu_shared.reputation.syncer import (
    ReputationSyncConfig,
    ReputationSyncer,
    ReputationSyncOutcome,
)

__all__ = [
    "DeviceReputationRow",
    "IpReputationRow",
    "ReputationSyncConfig",
    "ReputationSyncOutcome",
    "ReputationSyncer",
    "calc_score",
    "fetch_device_reputation",
    "fetch_ip_reputation",
]

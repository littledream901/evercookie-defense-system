"""ClickHouse 声誉物化视图的聚合查询与评分公式。

这是链路 ``decision_events`` → MV → 查询 → ProfileCache 的中间一段，
唯一一份实现。改这里等于同时改 worker 周期任务与 admin 手动触发。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class _Fetcher(Protocol):
    """只依赖 ``fetch`` 这一个方法，便于测试替身与两侧客户端复用。"""

    async def fetch(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class IpReputationRow:
    """一个「租户 + IP」维度的聚合结果。

    ``app_id`` 必须在这里出现：MV 的 ORDER BY 是 ``(log_date, site_id, ip)``，
    聚合时丢掉 site_id 有两个后果——多租户之间共享同一份 IP 声誉（A 站的爬虫
    流量压低 B 站对同一 IP 的评分），以及查询用不上主键前缀而每小时全表扫。
    
    注意：字段名保留 ``app_id`` 以保持向后兼容（admin-api 多处代码引用此字段），
    但查询的 MV 列名已改为 ``site_id``，通过 ``AS app_id`` 别名对齐。
    """

    app_id: int
    ip: str
    total: int
    blocked: int

    @property
    def score(self) -> float:
        return calc_score(self.total, self.blocked)


@dataclass(frozen=True, slots=True)
class DeviceReputationRow:
    """一个「租户 + 设备指纹」维度的聚合结果。"""

    app_id: int
    fingerprint: str
    total: int
    blocked: int

    @property
    def score(self) -> float:
        return calc_score(self.total, self.blocked)


# SummingMergeTree 的行在后台合并前是多份，必须 sum() + GROUP BY。
# 直接 SELECT total_count 只会拿到某个未合并分片的值，分数偏低且随合并进度
# 漂移——这种错误不报错，只让分数看起来「不太对」。
_IP_SQL = """
    SELECT
        site_id AS app_id,
        ip,
        sum(total_count)   AS total,
        sum(blocked_count) AS blocked
    FROM fangyu.mv_ip_reputation_daily
    WHERE log_date >= today() - {lookback_days}
      AND ip != ''
    GROUP BY site_id, ip
    HAVING total >= {min_samples}
"""

_DEVICE_SQL = """
    SELECT
        site_id AS app_id,
        fingerprint,
        sum(total_count)   AS total,
        sum(blocked_count) AS blocked
    FROM fangyu.mv_fingerprint_reputation_daily
    WHERE log_date >= today() - {lookback_days}
      AND fingerprint != ''
    GROUP BY site_id, fingerprint
    HAVING total >= {min_samples}
"""


async def fetch_ip_reputation(
    client: _Fetcher, *, lookback_days: int, min_samples: int
) -> list[IpReputationRow]:
    rows = await client.fetch(
        _IP_SQL, params={"lookback_days": lookback_days, "min_samples": min_samples}
    )
    return [
        IpReputationRow(
            app_id=int(r["app_id"]),
            ip=str(r["ip"]),
            total=int(r["total"]),
            blocked=int(r["blocked"]),
        )
        for r in rows
    ]


async def fetch_device_reputation(
    client: _Fetcher, *, lookback_days: int, min_samples: int
) -> list[DeviceReputationRow]:
    rows = await client.fetch(
        _DEVICE_SQL, params={"lookback_days": lookback_days, "min_samples": min_samples}
    )
    return [
        DeviceReputationRow(
            app_id=int(r["app_id"]),
            fingerprint=str(r["fingerprint"]),
            total=int(r["total"]),
            blocked=int(r["blocked"]),
        )
        for r in rows
    ]


def calc_score(total: int, blocked: int) -> float:
    """reputation_score = 100 - clamp(拦截率×100, 0, 100)。

    拦截率越高→信誉越低；全放行=100 分；全拦截=0 分。

    ``total <= 0`` 返回中性的 50 而不是 0：返回 0 会让没有任何样本的新 IP
    被当成「历史上全被拦过」的恶意 IP。消费侧另有 ``reputation_samples``
    区分「算出来正好 50」与「没数据用了默认 50」。

    结果保留两位小数以减少 Redis 中 JSON 的体积。
    """
    if total <= 0:
        return 50.0
    rate = min(1.0, max(0.0, blocked / total))
    return round(100.0 - rate * 100.0, 2)

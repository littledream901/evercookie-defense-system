"""分析查询规格（Query Object 模式）。

保持 domain 层不依赖具体存储，Repository/Service 负责翻译到 ClickHouse。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

TimeGranularity = Literal["minute", "hour", "day"]

TimelineDimension = Literal[
    "disposition",
    "is_bot",
    "crawler_category",
    "crawler_vendor",
]
"""时序图的分组维度。

``disposition`` 是历史默认值，按 verdict + mechanism 分组。爬虫三维度用于
渲染「爬虫流量趋势」——架构里要求的这张图此前无法出数据，因为时序查询只会
按处置分组。
"""

TopEntityDimension = Literal[
    "ip",
    "device",
    "country",
    "decided_by",
    "mechanism",
    "verdict",
    "is_bot",
    "crawler_category",
    "crawler_vendor",
]


@dataclass(frozen=True, slots=True)
class AnalyticsQuerySpec:
    app_id: Optional[int]
    start: datetime
    end: datetime
    filters: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("end 必须大于 start")


@dataclass(frozen=True, slots=True)
class DecisionTimelineSpec:
    base: AnalyticsQuerySpec
    granularity: TimeGranularity = "hour"
    dimension: TimelineDimension = "disposition"


@dataclass(frozen=True, slots=True)
class DispositionBreakdownSpec:
    base: AnalyticsQuerySpec


@dataclass(frozen=True, slots=True)
class TopEntitySpec:
    base: AnalyticsQuerySpec
    dimension: TopEntityDimension
    limit: int = 20


@dataclass(frozen=True, slots=True)
class RuleHitRateSpec:
    """规则命中率查询规格。

    读 ``mv_rule_hits_daily``（按天预聚合），因此时间范围以**日期**为粒度，
    而非主表查询的秒级 ``start``/``end``——用日粒度去读日聚合表才用得上它的
    主键前缀 ``(log_date, site_id, rule_id)``。
    """

    site_id: int | None
    start: datetime
    end: datetime
    limit: int = 50

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("end 必须大于 start")

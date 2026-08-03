"""分析查询规格（Query Object 模式）。

保持 domain 层不依赖具体存储，Repository/Service 负责翻译到 ClickHouse。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

TimeGranularity = Literal["minute", "hour", "day"]


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


@dataclass(frozen=True, slots=True)
class DispositionBreakdownSpec:
    base: AnalyticsQuerySpec


@dataclass(frozen=True, slots=True)
class TopEntitySpec:
    base: AnalyticsQuerySpec
    dimension: Literal["ip", "device", "country"]
    limit: int = 20

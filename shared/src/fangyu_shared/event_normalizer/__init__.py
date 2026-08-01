"""事件标准化子包.

用途:
    统一 Admin API 与 Worker 中事件字段的标准化逻辑，消除重复代码。
"""

from .constants import (
    DISPATCH_LABELS,
    DISPATCH_TYPE_MAP,
    IP_TYPE_LABELS,
)
from .normalizer import EventNormalizer
from .types import NormalizedEvent

__all__ = [
    "DISPATCH_LABELS",
    "DISPATCH_TYPE_MAP",
    "IP_TYPE_LABELS",
    "EventNormalizer",
    "NormalizedEvent",
]

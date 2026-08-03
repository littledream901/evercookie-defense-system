"""页面资源领域实体。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PageResourceKind(str, Enum):
    """资源投放目标。"""

    SAFE = "safe"
    """投给可信访客的内容（serve_alt 在正常分支时）。"""
    LANDING = "landing"
    """投给嫌疑访客的内容（serve_alt 在阻断/质疑分支时）。"""


@dataclass(slots=True)
class PageResource:
    """页面资源：serve_alt 机制的内容来源。"""

    id: int | None
    app_id: int
    name: str
    """资源标识符，对应 serve_alt(page=...) 的 page 参数。"""
    kind: PageResourceKind
    content: str
    content_type: str = "text/html; charset=utf-8"
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

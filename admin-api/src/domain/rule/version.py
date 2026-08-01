"""规则版本实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RuleVersion:
    id: int | None
    rule_id: int
    version: int
    snapshot: dict[str, Any] = field(default_factory=dict)
    author_id: int | None = None
    change_summary: str = ""
    created_at: datetime | None = None
    published_at: datetime | None = None

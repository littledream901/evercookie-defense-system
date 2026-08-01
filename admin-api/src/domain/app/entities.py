"""App 领域实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ApplicationStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


@dataclass(slots=True)
class Application:
    id: int | None
    name: str
    api_key: str
    owner_user_id: int
    status: ApplicationStatus = ApplicationStatus.ACTIVE
    description: str = ""
    domains: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

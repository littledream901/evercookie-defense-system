"""用户实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


@dataclass(slots=True)
class User:
    id: int | None
    username: str
    email: str
    password_hash: str
    display_name: str = ""
    status: UserStatus = UserStatus.ACTIVE
    role_ids: list[int] = field(default_factory=list)
    must_change_password: bool = True
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

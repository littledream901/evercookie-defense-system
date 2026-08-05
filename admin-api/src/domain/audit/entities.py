"""审计日志领域实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from fangyu_shared.utils.time import utcnow


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    ROTATE = "rotate"
    PUBLISH = "publish"
    DISABLE = "disable"
    OTHER = "other"


@dataclass(slots=True)
class AuditLog:
    id: int | None = None
    occurred_at: datetime = field(default_factory=utcnow)
    user_id: int | None = None
    username: str = ""
    method: str = ""
    path: str = ""
    resource: str = ""
    resource_id: str = ""
    action: str = AuditAction.OTHER.value
    status_code: int = 0
    ip: str = ""
    user_agent: str = ""
    request_id: str = ""
    detail: dict[str, Any] | None = None

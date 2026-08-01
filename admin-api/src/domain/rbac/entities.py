"""RBAC 领域实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Permission:
    """权限，格式：resource.action，例如 rule.publish、app.read。"""

    code: str
    description: str = ""

    def __post_init__(self) -> None:
        if "." not in self.code:
            raise ValueError(f"权限码需为 resource.action 形式: {self.code}")


@dataclass(slots=True)
class Role:
    id: int | None
    name: str
    description: str = ""
    is_system: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def has_permission(self, code: str) -> bool:
        return code in self.permissions or self._wildcard_match(code)

    def _wildcard_match(self, code: str) -> bool:
        resource = code.split(".", 1)[0]
        return f"{resource}.*" in self.permissions or "*" in self.permissions

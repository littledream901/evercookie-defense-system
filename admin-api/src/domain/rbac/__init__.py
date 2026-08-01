"""RBAC 领域。"""

from __future__ import annotations

from src.domain.rbac.entities import Permission, Role
from src.domain.rbac.policy import PermissionPolicy

__all__ = ["Permission", "PermissionPolicy", "Role"]

"""持久化仓储。"""

from __future__ import annotations

from src.infrastructure.repositories.application_repository import ApplicationRepository
from src.infrastructure.repositories.models import (
    ApplicationModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    RuleModel,
    RuleVersionModel,
    SiteModel,
    UserModel,
    UserRoleModel,
)
from src.infrastructure.repositories.rbac_repository import RbacRepository
from src.infrastructure.repositories.rule_repository import RuleAdminRepository
from src.infrastructure.repositories.site_repository import SiteRepository
from src.infrastructure.repositories.user_repository import UserRepository

__all__ = [
    "ApplicationModel",
    "ApplicationRepository",
    "PermissionModel",
    "RbacRepository",
    "RoleModel",
    "RolePermissionModel",
    "RuleAdminRepository",
    "RuleModel",
    "RuleVersionModel",
    "SiteModel",
    "SiteRepository",
    "UserModel",
    "UserRepository",
    "UserRoleModel",
]

"""领域实体 -> DTO 序列化辅助。"""

from __future__ import annotations

from src.domain.rbac.entities import Permission, Role
from src.domain.user.entities import User

from .schemas import PermissionSchema, RoleSchema, UserBriefSchema


def user_to_brief(user: User) -> UserBriefSchema:
    return UserBriefSchema(
        id=user.id or 0,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status.value,
        role_ids=list(user.role_ids),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def role_to_schema(role: Role) -> RoleSchema:
    return RoleSchema(
        id=role.id or 0,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=sorted(role.permissions),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def permission_to_schema(perm: Permission) -> PermissionSchema:
    return PermissionSchema(code=perm.code, description=perm.description)




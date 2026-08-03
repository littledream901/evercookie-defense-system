"""领域实体 -> DTO 序列化辅助。"""

from __future__ import annotations

from src.domain.app.entities import Application
from src.domain.rbac.entities import Permission, Role
from src.domain.user.entities import User

from .schemas import AppSchema, AppCreateResponse, PermissionSchema, RoleSchema, UserBriefSchema


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


def app_to_schema(app: Application, *, rule_name: str | None = None, rule_status: str | None = None) -> AppSchema:
    return AppSchema(
        id=app.id,
        site_id=app.site_id,
        app_secret=app.app_secret,
        name=app.name,
        domain=app.domain,
        alt_domains=app.alt_domains,
        access_mode=app.access_mode,
        status=app.status,
        sdk_version=app.sdk_version,
        gateway_url=app.gateway_url,
        is_active=app.is_active,
        owner_user_id=app.owner_user_id,
        clock_stats_enabled=app.clock_stats_enabled,
        log_retention_days=app.log_retention_days,
        remark=app.remark,
        created_at=app.created_at,
        updated_at=app.updated_at,
        rule_name=rule_name,
        rule_status=rule_status,
    )


def app_to_schema_with_secret(app: Application) -> AppSchema:
    """等同于 app_to_schema —— app_secret 已在基础序列化中明文回显。"""
    return app_to_schema(app)

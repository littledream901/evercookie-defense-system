"""seed default data

Revision ID: 20260731_0002
Revises: 20260731_0001
Create Date: 2026-07-31 00:00:02

内置：
- 权限清单（覆盖 v2 路由 require_permission 中全部 code）
- 系统角色：super_admin / admin / operator / auditor
- 角色 ↔ 权限绑定
- 默认超级管理员账号：admin / Admin@fangyu2026（首次登录必须改密）
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import bcrypt
from alembic import op
import sqlalchemy as sa


revision: str = "20260731_0002"
down_revision: Union[str, None] = "20260731_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PERMISSIONS: list[tuple[str, str]] = [
    ("user.read", "查看用户"),
    ("user.write", "创建/更新用户"),
    ("user.delete", "删除用户"),
    ("user.reset_password", "重置用户密码"),
    ("role.read", "查看角色"),
    ("role.write", "创建/更新角色"),
    ("role.delete", "删除角色"),
    ("permission.read", "查看权限"),
    ("permission.write", "维护权限元数据"),
    ("app.read", "查看应用"),
    ("app.write", "创建/更新应用"),
    ("app.delete", "删除应用"),
    ("app.rotate_key", "轮换应用 API Key"),
    ("rule.read", "查看规则"),
    ("rule.write", "创建/更新规则"),
    ("rule.delete", "删除规则"),
    ("rule.publish", "发布/回滚/同步规则"),
    ("analytics.read", "查看分析数据"),
    ("audit.read", "查看审计日志"),
]

_ROLES: list[tuple[str, str, bool]] = [
    ("super_admin", "超级管理员，拥有全部权限", True),
    ("admin", "管理员，除权限元数据外拥有大部分权限", True),
    ("operator", "运营，管理规则与应用", True),
    ("auditor", "审计，只读", True),
]

_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ["*"],
    "admin": [
        "user.read",
        "user.write",
        "user.reset_password",
        "role.read",
        "app.*",
        "rule.*",
        "analytics.read",
        "audit.read",
    ],
    "operator": [
        "app.read",
        "app.write",
        "rule.*",
        "analytics.read",
    ],
    "auditor": [
        "user.read",
        "role.read",
        "app.read",
        "rule.read",
        "analytics.read",
        "audit.read",
    ],
}

_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@fangyu.local")
_DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "Admin@fangyu2026")


def _hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upgrade() -> None:
    conn = op.get_bind()

    sys_permission = sa.table(
        "sys_permission",
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    conn.execute(
        sys_permission.insert(),
        [{"code": code, "description": desc} for code, desc in _PERMISSIONS],
    )

    sys_role = sa.table(
        "sys_role",
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
    )
    conn.execute(
        sys_role.insert(),
        [
            {"name": name, "description": desc, "is_system": is_sys}
            for name, desc, is_sys in _ROLES
        ],
    )

    role_rows = conn.execute(
        sa.text("SELECT id, name FROM sys_role WHERE name IN :names").bindparams(
            sa.bindparam("names", expanding=True)
        ),
        {"names": [r[0] for r in _ROLES]},
    ).fetchall()
    role_id_by_name = {row.name: row.id for row in role_rows}

    sys_role_permission = sa.table(
        "sys_role_permission",
        sa.column("role_id", sa.BigInteger),
        sa.column("permission_code", sa.String),
    )
    binding_rows: list[dict] = []
    for role_name, codes in _ROLE_PERMISSIONS.items():
        role_id = role_id_by_name.get(role_name)
        if role_id is None:
            continue
        for code in codes:
            binding_rows.append({"role_id": role_id, "permission_code": code})
    if binding_rows:
        conn.execute(sys_role_permission.insert(), binding_rows)

    sys_user = sa.table(
        "sys_user",
        sa.column("username", sa.String),
        sa.column("email", sa.String),
        sa.column("display_name", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("status", sa.String),
    )
    conn.execute(
        sys_user.insert(),
        [
            {
                "username": _DEFAULT_ADMIN_USERNAME,
                "email": _DEFAULT_ADMIN_EMAIL,
                "display_name": "系统超级管理员",
                "password_hash": _hash_password(_DEFAULT_ADMIN_PASSWORD),
                "status": "active",
            }
        ],
    )

    admin_row = conn.execute(
        sa.text("SELECT id FROM sys_user WHERE username = :u"),
        {"u": _DEFAULT_ADMIN_USERNAME},
    ).fetchone()
    super_admin_id = role_id_by_name.get("super_admin")
    if admin_row is not None and super_admin_id is not None:
        conn.execute(
            sa.text(
                "INSERT INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"
            ),
            {"uid": admin_row.id, "rid": super_admin_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM sys_user_role"))
    conn.execute(sa.text("DELETE FROM sys_user WHERE username = :u"), {"u": _DEFAULT_ADMIN_USERNAME})
    conn.execute(sa.text("DELETE FROM sys_role_permission"))
    conn.execute(sa.text("DELETE FROM sys_role"))
    conn.execute(sa.text("DELETE FROM sys_permission"))

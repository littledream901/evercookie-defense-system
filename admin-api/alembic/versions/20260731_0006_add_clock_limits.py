"""add clock limits table and permissions

Revision ID: 20260731_0006
Revises: 20260731_0005
Create Date: 2026-07-31

新增:
- biz_clock_limits 表（Clock 阈值持久化）
- clock.read / clock.write 权限
- 修复遗漏: threat_intel.read / threat_intel.write 权限（seed 0002 漏植）
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0006"
down_revision: Union[str, None] = "20260731_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMISSIONS: list[tuple[str, str]] = [
    ("clock.read", "查看 Clock 阈值与封禁"),
    ("clock.write", "更新 Clock 阈值与封禁"),
    ("threat_intel.read", "查看威胁情报"),
    ("threat_intel.write", "创建/更新/删除威胁情报"),
]

_ROLE_ADDITIONS: dict[str, list[str]] = {
    "admin": ["clock.read", "clock.write", "threat_intel.read", "threat_intel.write"],
    "operator": ["clock.read", "clock.write", "threat_intel.read", "threat_intel.write"],
    "auditor": ["clock.read", "threat_intel.read"],
}


def upgrade() -> None:
    op.create_table(
        "biz_clock_limits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("windows", sa.JSON(), nullable=False),
        sa.Column("ban_seconds", sa.Integer(), nullable=False, server_default="900"),
        sa.Column("ban_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("app_id", name="uk_clock_limits_app"),
    )

    conn = op.get_bind()

    sys_permission = sa.table(
        "sys_permission",
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    conn.execute(
        sys_permission.insert(),
        [{"code": code, "description": desc} for code, desc in _NEW_PERMISSIONS],
    )

    role_rows = conn.execute(
        sa.text("SELECT id, name FROM sys_role WHERE name IN :names").bindparams(
            sa.bindparam("names", expanding=True)
        ),
        {"names": list(_ROLE_ADDITIONS.keys())},
    ).fetchall()
    role_id_by_name = {row.name: row.id for row in role_rows}

    sys_role_permission = sa.table(
        "sys_role_permission",
        sa.column("role_id", sa.BigInteger),
        sa.column("permission_code", sa.String),
    )
    binding_rows: list[dict] = []
    for role_name, codes in _ROLE_ADDITIONS.items():
        role_id = role_id_by_name.get(role_name)
        if role_id is None:
            continue
        for code in codes:
            binding_rows.append({"role_id": role_id, "permission_code": code})
    if binding_rows:
        conn.execute(sys_role_permission.insert(), binding_rows)


def downgrade() -> None:
    conn = op.get_bind()
    codes = [code for code, _ in _NEW_PERMISSIONS]
    conn.execute(
        sa.text("DELETE FROM sys_role_permission WHERE permission_code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": codes},
    )
    conn.execute(
        sa.text("DELETE FROM sys_permission WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": codes},
    )
    op.drop_table("biz_clock_limits")

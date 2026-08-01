"""add sys_audit_log & seed audit permission

Revision ID: 20260731_0003
Revises: 20260731_0002
Create Date: 2026-07-31 00:00:03

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON as MySQLJSON


revision: str = "20260731_0003"
down_revision: Union[str, None] = "20260731_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("method", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("path", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("resource", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("resource_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("detail", MySQLJSON(), nullable=True),
        sa.Index("idx_audit_occurred", "occurred_at"),
        sa.Index("idx_audit_user", "user_id", "occurred_at"),
        sa.Index("idx_audit_resource", "resource", "occurred_at"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 审计查询权限沿用 seed 0002 已植入的 audit.read，不再新造 audit_log.view：
    # 两个码指向同一能力会导致角色授了一个、路由校验另一个，表现为「有权限却 403」。
    # sys_role_permission 以 permission_code 关联（非 permission_id），
    # sys_permission 也只有 code / description 两个业务列。
    conn = op.get_bind()
    role_row = conn.execute(
        sa.text("SELECT id FROM sys_role WHERE name = :n"),
        {"n": "super_admin"},
    ).fetchone()
    if role_row is not None:
        existing = conn.execute(
            sa.text(
                "SELECT id FROM sys_role_permission "
                "WHERE role_id = :rid AND permission_code = :c"
            ),
            {"rid": role_row.id, "c": "audit.read"},
        ).fetchone()
        if existing is None:
            conn.execute(
                sa.text(
                    "INSERT INTO sys_role_permission (role_id, permission_code) "
                    "VALUES (:rid, :c)"
                ),
                {"rid": role_row.id, "c": "audit.read"},
            )


def downgrade() -> None:
    op.drop_table("sys_audit_log")

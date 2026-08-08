"""add user api key table

Revision ID: 20260807_0022
Revises: 20260804_0021
Create Date: 2026-08-07

添加用户 API Key 表，用于用户级别的 API 访问认证。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0022"
down_revision: Union[str, None] = "20260804_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_user_api_key",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("key_hash", name="uk_user_api_key_hash"),
    )
    op.create_index("idx_user_api_key_user", "sys_user_api_key", ["user_id"])
    op.create_index("idx_user_api_key_key_hash", "sys_user_api_key", ["key_hash"])


def downgrade() -> None:
    op.drop_index("idx_user_api_key_key_hash", table_name="sys_user_api_key")
    op.drop_index("idx_user_api_key_user", table_name="sys_user_api_key")
    op.drop_table("sys_user_api_key")

"""add biz_page_resource table

Revision ID: 20260801_0009
Revises: 20260801_0008
Create Date: 2026-08-01

biz_page_resource 存储 serve_alt 机制的内容来源。
admin 侧 CRUD 后同步到 Redis，gateway serve_alt 命中时按资源名取内容回传。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0009"
down_revision: Union[str, None] = "20260801_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "biz_page_resource",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="safe"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False,
                  server_default="text/html; charset=utf-8"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"),
                  onupdate=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["app_id"], ["biz_application.id"]),
        sa.UniqueConstraint("app_id", "name", name="uk_page_resource_app_name"),
    )
    op.create_index("ix_page_resource_app_enabled", "biz_page_resource", ["app_id", "enabled"])


def downgrade() -> None:
    op.drop_index("ix_page_resource_app_enabled", table_name="biz_page_resource")
    op.drop_table("biz_page_resource")

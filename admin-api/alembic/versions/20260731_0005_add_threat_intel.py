"""add threat intel table

Revision ID: 20260731_0005
Revises: 20260731_0004
Create Date: 2026-07-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260731_0005"
down_revision = "20260731_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_threat_intel",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="malicious"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ip", name="uk_threat_intel_ip"),
    )
    op.create_index("ix_threat_intel_category", "biz_threat_intel", ["category"])
    op.create_index("ix_threat_intel_source", "biz_threat_intel", ["source"])
    op.create_index("ix_threat_intel_active", "biz_threat_intel", ["is_active"])


def downgrade() -> None:
    op.drop_table("biz_threat_intel")

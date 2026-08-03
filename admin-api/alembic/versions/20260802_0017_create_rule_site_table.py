"""B--: create biz_rule_site join table (was missing from migrations).

Revision ID: 20260802_0017
Revises: 20260802_0016
Create Date: 2026-08-02

biz_rule_site 是规则多对多关联表，ORM 已有 RuleSiteModel 但 DB 中表不存在，
导致 GET /rules 时 _site_ids_map 查询报 1146 "Table doesn't exist"。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260802_0017"
down_revision = "20260802_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biz_rule_site",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["biz_rule.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["biz_application.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "site_id", name="uk_rule_site"),
    )
    op.create_index("ix_biz_rule_site_site", "biz_rule_site", ["site_id"])


def downgrade() -> None:
    op.drop_table("biz_rule_site")

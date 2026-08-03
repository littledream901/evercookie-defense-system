"""rename biz_rule.app_id → site_id

Revision ID: 20260802_0012
Revises: 20260802_0011
Create Date: 2026-08-02

站点管理主键语义变更：rule 表的外键列由 app_id 改名为 site_id，
含义更清晰（对应 biz_application.id 整数主键）。
同步重建索引名称。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0012"
down_revision: Union[str, None] = "20260802_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL 不允许删除被外键引用的索引，需先删 FK → 删旧索引 → 改列名 → 建新索引 → 重建 FK
    op.drop_constraint("fk_biz_rule_app", "biz_rule", type_="foreignkey")
    op.drop_index("ix_biz_rule_app_status", table_name="biz_rule")
    op.alter_column(
        "biz_rule",
        "app_id",
        new_column_name="site_id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.create_index("ix_biz_rule_site_status", "biz_rule", ["site_id", "status"])
    op.create_foreign_key(
        "fk_biz_rule_app", "biz_rule", "biz_application", ["site_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_biz_rule_app", "biz_rule", type_="foreignkey")
    op.drop_index("ix_biz_rule_site_status", table_name="biz_rule")
    op.alter_column(
        "biz_rule",
        "site_id",
        new_column_name="app_id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.create_index("ix_biz_rule_app_status", "biz_rule", ["app_id", "status"])
    op.create_foreign_key(
        "fk_biz_rule_app", "biz_rule", "biz_application", ["app_id"], ["id"]
    )

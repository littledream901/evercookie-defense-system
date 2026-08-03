"""split biz_rule.disposition into disposition_match / disposition_miss

Revision ID: 20260802_0011
Revises: 20260802_0010
Create Date: 2026-08-02

旧模型用单个 disposition JSON 列表达处置，新模型拆成：
  - disposition_match: 命中时的处置（继承旧 disposition 的值）
  - disposition_miss:  未命中时的处置（默认 pass 放行）

同时旧列 disposition 在 0007 里已升为 JSON，本次迁移将其删除。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import JSON as MySQLJSON

revision: str = "20260802_0011"
down_revision: Union[str, None] = "20260802_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PASS_DISPOSITION = '{"mechanism": "pass", "ttlSeconds": 300}'


def upgrade() -> None:
    op.add_column(
        "biz_rule",
        sa.Column("disposition_match", MySQLJSON(), nullable=True),
    )
    op.add_column(
        "biz_rule",
        sa.Column("disposition_miss", MySQLJSON(), nullable=True),
    )

    # 将旧 disposition 值迁移到 disposition_match
    op.execute(
        "UPDATE biz_rule SET disposition_match = disposition WHERE disposition IS NOT NULL"
    )
    # 未命中默认放行
    op.execute(
        f"UPDATE biz_rule SET disposition_miss = '{_PASS_DISPOSITION}'"
    )

    op.drop_column("biz_rule", "disposition")


def downgrade() -> None:
    op.add_column(
        "biz_rule",
        sa.Column("disposition", MySQLJSON(), nullable=True),
    )
    op.execute(
        "UPDATE biz_rule SET disposition = disposition_match"
    )
    op.drop_column("biz_rule", "disposition_miss")
    op.drop_column("biz_rule", "disposition_match")

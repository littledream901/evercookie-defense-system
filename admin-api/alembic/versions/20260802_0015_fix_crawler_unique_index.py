"""M-09: biz_intel_crawler 补 feature_type + pattern 联合唯一索引。

Revision ID: 20260802_0015
Revises: 20260802_0014
Create Date: 2026-08-02

当前 IntelRepository._UNIQUE_KEY[crawler] = "pattern" 只按 pattern 查唯一，
但 DB 层没有对应约束，可能造成相同 pattern 写入多条不同 feature_type 的记录。
本迁移补建联合唯一索引。
"""
from __future__ import annotations

from alembic import op

revision = "20260802_0015"
down_revision = "20260802_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("biz_intel_crawler") as batch_op:
        batch_op.create_unique_constraint(
            "uq_intel_crawler_feature_pattern",
            ["feature_type", "pattern"],
        )


def downgrade() -> None:
    with op.batch_alter_table("biz_intel_crawler") as batch_op:
        batch_op.drop_constraint("uq_intel_crawler_feature_pattern", type_="unique")

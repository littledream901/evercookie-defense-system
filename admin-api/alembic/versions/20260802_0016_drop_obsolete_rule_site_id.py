"""B-rule: drop obsolete biz_rule.site_id after many-to-many refactoring.

Revision ID: 20260802_0016
Revises: 20260802_0015
Create Date: 2026-08-02

规则系统已从 1:1（biz_rule.site_id）改为多对多（biz_rule_site 关联表）。
ORM 模型 RuleModel 不再映射该列，但 DB 中 site_id 仍为 NOT NULL 无默认值，
导致 INSERT 时报 1364 "Field 'site_id' doesn't have a default value"。

本迁移删除该废弃列及关联的外键与索引。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260802_0016"
down_revision: Union[str, None] = "20260802_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_biz_rule_app", "biz_rule", type_="foreignkey")
    op.drop_index("ix_biz_rule_site_status", table_name="biz_rule")
    op.drop_column("biz_rule", "site_id")


def downgrade() -> None:
    pass  # 此列已废弃，不回滚

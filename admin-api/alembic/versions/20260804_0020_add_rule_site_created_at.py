"""补齐 biz_rule_site.created_at（ORM 已声明但建表迁移漏掉）。

Revision ID: 20260804_0020
Revises: 20260803_0019
Create Date: 2026-08-04

0017 创建 biz_rule_site 时只建了 id / rule_id / site_id 三列，
但 ORM 的 RuleSiteModel 声明了 created_at（NOT NULL、Python 侧
default=local_now、无 server_default）。

于是每次 INSERT 都会带上 created_at 字段，而 DB 里没有这一列，
报 1054 "Unknown column 'created_at' in 'field list'"：

    INSERT INTO biz_rule_site (rule_id, site_id, created_at) VALUES (...)

读路径（list_site_ids / _site_ids_map）只 SELECT rule_id, site_id，
所以此前一直没暴露，只有绑定规则到站点时才炸。

本迁移带 server_default=CURRENT_TIMESTAMP 添加该列：
  1. 已有行会被回填为迁移执行时刻，避免 NOT NULL 加列失败；
  2. 保留 server_default 与 TimestampMixin 的其他表行为一致，
     即使将来有人绕过 ORM 直接 INSERT 也不会失败。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260804_0020"
down_revision = "20260803_0019"
branch_labels = None
depends_on = None

TABLE = "biz_rule_site"
COLUMN = "created_at"


def _has_column() -> bool:
    """兼容用 create_all 建过库、已存在该列的环境。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return True  # 表不存在则无需处理，交由 0017 负责
    return any(col["name"] == COLUMN for col in inspector.get_columns(TABLE))


def upgrade() -> None:
    if _has_column():
        return
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    if not _has_column():
        return
    op.drop_column(TABLE, COLUMN)

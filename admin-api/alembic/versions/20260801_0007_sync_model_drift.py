"""sync model drift

Revision ID: 20260801_0007
Revises: 20260731_0006
Create Date: 2026-08-01 16:56:22.709283

修复模型与迁移脱节导致的 schema 漂移。真实差异只有以下几类，
autogenerate 报出的大量 server_default 差异是 Alembic 对 MySQL
`now()` 与 `(now())` 表达式的误判，已剔除：

1. biz_rule 缺 kind / match_all / rule_group 三列（导致规则列表接口 500）
2. biz_rule.disposition 需从 VARCHAR(32) 升级为 JSON（承载三层处置结构）
3. biz_rule_group 表整体缺失
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "20260801_0007"
down_revision: Union[str, None] = "20260731_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "biz_rule_group",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="blocklist"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("on_no_match", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["biz_application.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "name", name="uk_rule_group_app_name"),
    )

    op.add_column(
        "biz_rule",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="decision"),
    )
    op.add_column(
        "biz_rule",
        sa.Column("match_all", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("biz_rule", sa.Column("rule_group", sa.String(length=64), nullable=True))

    # 老列是 VARCHAR(32) 存单个动作名，新结构存 verdict/mechanism/target 三层 JSON。
    # 先清空再改类型：存量数据是 'ALLOW' 之类的裸串，无法被 JSON 解析。
    op.execute("UPDATE biz_rule SET disposition = NULL")
    op.alter_column(
        "biz_rule",
        "disposition",
        existing_type=mysql.VARCHAR(length=32),
        type_=mysql.JSON(),
        server_default=None,
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE biz_rule SET disposition = NULL")
    op.alter_column(
        "biz_rule",
        "disposition",
        existing_type=mysql.JSON(),
        type_=mysql.VARCHAR(length=32),
        server_default=sa.text("'ALLOW'"),
        nullable=False,
    )
    op.drop_column("biz_rule", "rule_group")
    op.drop_column("biz_rule", "match_all")
    op.drop_column("biz_rule", "kind")
    op.drop_table("biz_rule_group")

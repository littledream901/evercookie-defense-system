"""rebuild biz_application schema

Revision ID: 20260802_0010
Revises: 20260801_0009
Create Date: 2026-08-02

将 biz_application 从旧列结构（api_key / status / description / domains）
对齐到当前 ORM 模型（site_id / is_active / alt_domains / ...）。

site_id 同时兼任 X-App-Key（API Key），不再有独立的 app_id 列。

升级步骤
--------
1. 新增所有新列（带 server_default 保证存量行不违反 NOT NULL）
2. 将存量数据从旧列迁移到新列：
   - site_id  ← 生成 site_<hex8>，兼任 X-App-Key
   - is_active ← status == 'active'
   - domain   ← 取 domains JSON 数组第一个元素，若无则留 ''
   - alt_domains ← domains JSON 数组其余元素
3. 添加新唯一约束
4. 删除旧列（api_key / status / description / domains）
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import JSON as MySQLJSON

revision: str = "20260802_0010"
down_revision: Union[str, None] = "20260801_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "biz_application",
        sa.Column("site_id", sa.String(32), nullable=False, server_default=""),
    )
    op.add_column(
        "biz_application",
        sa.Column("domain", sa.String(512), nullable=False, server_default=""),
    )
    op.add_column(
        "biz_application",
        sa.Column("alt_domains", MySQLJSON(), nullable=True),
    )
    op.execute("UPDATE biz_application SET alt_domains = JSON_ARRAY() WHERE alt_domains IS NULL")
    op.add_column(
        "biz_application",
        sa.Column("access_mode", sa.String(16), nullable=False, server_default="cloud"),
    )
    op.add_column(
        "biz_application",
        sa.Column("sdk_version", sa.String(16), nullable=True),
    )
    op.add_column(
        "biz_application",
        sa.Column("cname_value", sa.String(256), nullable=True),
    )
    op.add_column(
        "biz_application",
        sa.Column("gateway_url", sa.String(512), nullable=True),
    )
    op.add_column(
        "biz_application",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "biz_application",
        sa.Column("rule_mode", sa.String(16), nullable=False, server_default="global"),
    )
    op.add_column(
        "biz_application",
        sa.Column("rule_template_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "biz_application",
        sa.Column("clock_stats_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "biz_application",
        sa.Column("log_retention_days", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "biz_application",
        sa.Column("remark", sa.Text(), nullable=True),
    )

    op.execute(
        "UPDATE biz_application "
        "SET site_id = CONCAT('site_', LOWER(LEFT(REPLACE(UUID(), '-', ''), 8))) "
        "WHERE site_id = ''"
    )
    op.execute(
        "UPDATE biz_application SET is_active = (status = 'active')"
    )
    op.execute(
        "UPDATE biz_application "
        "SET domain = COALESCE(JSON_UNQUOTE(JSON_EXTRACT(domains, '$[0]')), '') "
        "WHERE domains IS NOT NULL AND JSON_LENGTH(domains) >= 1"
    )
    op.execute(
        "UPDATE biz_application "
        "SET alt_domains = COALESCE(JSON_EXTRACT(domains, '$[1 to last]'), '[]') "
        "WHERE domains IS NOT NULL AND JSON_LENGTH(domains) >= 2"
    )

    op.create_unique_constraint("uk_biz_application_site_id", "biz_application", ["site_id"])

    op.drop_constraint("uk_biz_application_api_key", "biz_application", type_="unique")
    op.drop_column("biz_application", "api_key")
    op.drop_column("biz_application", "status")
    op.drop_column("biz_application", "description")
    op.drop_column("biz_application", "domains")


def downgrade() -> None:
    op.add_column(
        "biz_application",
        sa.Column("api_key", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "biz_application",
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    op.add_column(
        "biz_application",
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
    )
    op.add_column(
        "biz_application",
        sa.Column("domains", MySQLJSON(), nullable=True),
    )

    op.execute(
        "UPDATE biz_application SET api_key = site_id, "
        "status = IF(is_active, 'active', 'paused'), "
        "domains = JSON_ARRAY(domain)"
    )

    op.create_unique_constraint("uk_biz_application_api_key", "biz_application", ["api_key"])

    op.drop_constraint("uk_biz_application_site_id", "biz_application", type_="unique")
    op.drop_column("biz_application", "site_id")
    op.drop_column("biz_application", "domain")
    op.drop_column("biz_application", "alt_domains")
    op.drop_column("biz_application", "access_mode")
    op.drop_column("biz_application", "sdk_version")
    op.drop_column("biz_application", "cname_value")
    op.drop_column("biz_application", "gateway_url")
    op.drop_column("biz_application", "is_active")
    op.drop_column("biz_application", "rule_mode")
    op.drop_column("biz_application", "rule_template_id")
    op.drop_column("biz_application", "clock_stats_enabled")
    op.drop_column("biz_application", "log_retention_days")
    op.drop_column("biz_application", "remark")

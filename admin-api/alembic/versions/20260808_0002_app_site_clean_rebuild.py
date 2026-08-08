"""app-site separation v2: clean rebuild

Revision ID: 20260808_0002
Revises: 20260807_0022
Create Date: 2026-08-08

简化版本：删除旧表，从头创建新的 App-Site 两层架构
适用于测试环境，可清空数据
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260808_0002"
down_revision: Union[str, None] = "20260807_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================== 阶段 1：删除旧表和约束 ====================
    
    # 1.1 删除规则相关的外键约束
    op.execute("SET FOREIGN_KEY_CHECKS=0")
    
    # 1.2 删除所有可能的旧表
    op.execute("DROP TABLE IF EXISTS _migration_app_site_mapping")
    op.execute("DROP TABLE IF EXISTS biz_application_old")
    op.execute("DROP TABLE IF EXISTS biz_site")
    op.execute("DROP TABLE IF EXISTS biz_rule_site")
    op.execute("DROP TABLE IF EXISTS biz_rule_group")
    op.execute("DROP TABLE IF EXISTS biz_rule")
    op.execute("DROP TABLE IF EXISTS biz_application")
    
    op.execute("SET FOREIGN_KEY_CHECKS=1")
    
    # ==================== 阶段 2：创建新的 Application 表（应用层） ====================
    
    op.create_table(
        "biz_application",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_key", sa.String(32), nullable=False, comment="应用唯一标识 app_<hex8>"),
        sa.Column("name", sa.String(128), nullable=False, comment="应用名称"),
        sa.Column("description", sa.String(512), server_default="", nullable=False, comment="应用描述"),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True, comment="应用所有者"),
        sa.Column("app_secret", sa.String(128), nullable=False, comment="应用级密钥"),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False, comment="是否启用"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_key", name="uk_app_key"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="应用表（业务分组）"
    )
    op.create_index("idx_app_owner", "biz_application", ["owner_user_id"])
    op.create_index("idx_app_active", "biz_application", ["is_active"])
    
    # ==================== 阶段 3：创建新的 Site 表（站点层） ====================
    
    op.create_table(
        "biz_site",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_key", sa.String(32), nullable=False, comment="站点唯一标识 site_<hex8>"),
        sa.Column("app_id", sa.BigInteger(), nullable=False, comment="所属应用"),
        sa.Column("name", sa.String(128), nullable=False, comment="站点名称"),
        sa.Column("domain", sa.String(512), nullable=False, comment="主域名"),
        sa.Column("alt_domains", mysql.JSON(), nullable=False, comment="备用域名列表"),
        sa.Column("access_mode", sa.String(16), server_default="adapter", nullable=False, comment="接入模式：adapter/sdk"),
        sa.Column("site_secret", sa.String(128), server_default="", nullable=False, comment="站点级密钥"),
        sa.Column("sdk_version", sa.String(16), nullable=True, comment="SDK 版本"),
        sa.Column("gateway_url", sa.String(512), nullable=True, comment="专属网关地址"),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False, comment="是否启用"),
        sa.Column("clock_stats_enabled", sa.Boolean(), server_default="1", nullable=False, comment="是否启用频控统计"),
        sa.Column("log_retention_days", sa.Integer(), server_default="30", nullable=False, comment="日志保留天数"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_key", name="uk_site_key"),
        sa.ForeignKeyConstraint(["app_id"], ["biz_application.id"], name="fk_site_app", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="站点表（具体站点）"
    )
    op.create_index("idx_site_app", "biz_site", ["app_id"])
    op.create_index("idx_site_domain", "biz_site", [sa.text("domain(255)")])
    op.create_index("idx_site_active", "biz_site", ["is_active"])
    
    # ==================== 阶段 4：重建 Rule 表 ====================
    
    op.create_table(
        "biz_rule",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=True, comment="应用级规则（为空则全局规则）"),
        sa.Column("name", sa.String(128), nullable=False, comment="规则名称"),
        sa.Column("conditions", mysql.JSON(), nullable=False, comment="规则条件"),
        sa.Column("verdict", sa.String(16), nullable=False, comment="判决结果"),
        sa.Column("mechanism", sa.String(16), nullable=False, comment="处置机制"),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False, comment="优先级"),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False, comment="状态"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["app_id"], ["biz_application.id"], name="fk_rule_app", ondelete="SET NULL"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则表"
    )
    op.create_index("idx_rule_app", "biz_rule", ["app_id"])
    op.create_index("idx_rule_status", "biz_rule", ["status"])
    
    # ==================== 阶段 5：重建 Rule-Site 关联表 ====================
    
    op.create_table(
        "biz_rule_site",
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("rule_id", "site_id"),
        sa.ForeignKeyConstraint(["rule_id"], ["biz_rule.id"], name="fk_rule_site_rule", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["biz_site.id"], name="fk_rule_site_site", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则-站点关联表"
    )
    
    # ==================== 阶段 6：重建 Rule Group 表 ====================
    
    op.create_table(
        "biz_rule_group",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False, comment="所属站点"),
        sa.Column("name", sa.String(128), nullable=False, comment="规则组名称"),
        sa.Column("description", sa.String(512), server_default="", nullable=False, comment="描述"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["site_id"], ["biz_site.id"], name="fk_rule_group_site", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则组表"
    )
    op.create_index("idx_rule_group_site", "biz_rule_group", ["site_id"])
    
    # ==================== 阶段 7：插入示例数据 ====================
    
    # 创建默认应用
    op.execute("""
        INSERT INTO biz_application (app_key, name, description, app_secret, is_active)
        VALUES ('app_default', '默认应用', '系统默认应用', 'default_secret_key', 1)
    """)
    
    # 创建默认站点
    op.execute("""
        INSERT INTO biz_site (site_key, app_id, name, domain, alt_domains, access_mode, is_active)
        SELECT 'site_default', id, '默认站点', 'localhost', '[]', 'adapter', 1
        FROM biz_application WHERE app_key = 'app_default'
    """)


def downgrade() -> None:
    # 回滚：删除所有新表
    op.execute("SET FOREIGN_KEY_CHECKS=0")
    op.execute("DROP TABLE IF EXISTS biz_rule_group")
    op.execute("DROP TABLE IF EXISTS biz_rule_site")
    op.execute("DROP TABLE IF EXISTS biz_rule")
    op.execute("DROP TABLE IF EXISTS biz_site")
    op.execute("DROP TABLE IF EXISTS biz_application")
    op.execute("SET FOREIGN_KEY_CHECKS=1")

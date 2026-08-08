"""app-site separation v3: two-tier architecture

Revision ID: 20260808_0002
Revises: 20260807_0022
Create Date: 2026-08-08

V3 两层架构迁移：
- 重建 biz_application 表（应用层）
- 新建 biz_site 表（站点层）
- 更新 biz_rule 表支持 app_id
- 更新 biz_rule_site 和 biz_rule_group 外键关联

警告：此迁移会删除旧表数据，仅适用于测试环境
生产环境请使用数据迁移方案
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
    # ==================== 阶段 1：备份和删除旧表 ====================
    
    # 1.1 禁用外键检查
    op.execute("SET FOREIGN_KEY_CHECKS=0")
    
    # 1.2 备份旧表（可选，生产环境建议手动备份）
    # op.execute("CREATE TABLE biz_application_backup AS SELECT * FROM biz_application")
    
    # 1.3 删除所有相关旧表
    op.execute("DROP TABLE IF EXISTS _migration_app_site_mapping")
    op.execute("DROP TABLE IF EXISTS biz_application_old")
    op.execute("DROP TABLE IF EXISTS biz_rule_version")
    op.execute("DROP TABLE IF EXISTS biz_rule_site")
    op.execute("DROP TABLE IF EXISTS biz_rule_group")
    op.execute("DROP TABLE IF EXISTS biz_rule")
    op.execute("DROP TABLE IF EXISTS biz_site")
    op.execute("DROP TABLE IF EXISTS biz_application")
    
    # 1.4 重新启用外键检查
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
    
    # ==================== 阶段 4：重建 Rule 表（支持应用级规则） ====================
    
    op.create_table(
        "biz_rule",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False, comment="规则名称"),
        sa.Column("description", sa.String(512), server_default="", nullable=False, comment="规则描述"),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False, comment="状态：draft/published/shadow/archived"),
        sa.Column("priority", sa.String(16), server_default="normal", nullable=False, comment="优先级：low/normal/high/critical"),
        sa.Column("kind", sa.String(16), server_default="decision", nullable=False, comment="规则类型：decision/scoring"),
        sa.Column("weight", sa.Integer(), server_default="0", nullable=False, comment="评分权重"),
        sa.Column("disposition_match", mysql.JSON(), nullable=True, comment="命中时的处置动作"),
        sa.Column("disposition_miss", mysql.JSON(), nullable=True, comment="未命中时的处置动作"),
        sa.Column("conditions", mysql.JSON(), nullable=False, comment="规则条件"),
        sa.Column("match_all", sa.Boolean(), server_default="1", nullable=False, comment="是否全部匹配"),
        sa.Column("rule_group", sa.String(64), nullable=True, comment="所属规则组"),
        sa.Column("tags", mysql.JSON(), nullable=False, comment="标签列表"),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False, comment="版本号"),
        sa.Column("published_at", sa.DateTime(), nullable=True, comment="发布时间"),
        sa.Column("app_id", sa.BigInteger(), nullable=True, comment="应用级规则（为空则全局规则）"),
        sa.Column("inherit_from_app", sa.Boolean(), server_default="0", nullable=False, comment="站点是否继承应用规则"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["app_id"], ["biz_application.id"], name="fk_rule_app", ondelete="SET NULL"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则表"
    )
    op.create_index("idx_rule_app_id", "biz_rule", ["app_id"])
    op.create_index("idx_rule_status", "biz_rule", ["status"])
    
    # ==================== 阶段 5：重建 Rule-Site 关联表 ====================
    
    op.create_table(
        "biz_rule_site",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "site_id", name="uk_rule_site"),
        sa.ForeignKeyConstraint(["rule_id"], ["biz_rule.id"], name="fk_rule_site_rule", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["biz_site.id"], name="fk_rule_site_site", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则-站点关联表"
    )
    op.create_index("idx_rule_site_site", "biz_rule_site", ["site_id"])
    
    # ==================== 阶段 6：重建 Rule Group 表 ====================
    
    op.create_table(
        "biz_rule_group",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False, comment="所属站点"),
        sa.Column("name", sa.String(64), nullable=False, comment="规则组名称"),
        sa.Column("mode", sa.String(16), server_default="blocklist", nullable=False, comment="模式：blocklist/allowlist"),
        sa.Column("priority", sa.String(16), server_default="normal", nullable=False, comment="优先级"),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False, comment="是否启用"),
        sa.Column("on_no_match", mysql.JSON(), nullable=True, comment="allowlist 模式下组内全未命中时的处置"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "name", name="uk_rule_group_site_name"),
        sa.ForeignKeyConstraint(["site_id"], ["biz_site.id"], name="fk_rule_group_site", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则组表"
    )
    op.create_index("idx_rule_group_site", "biz_rule_group", ["site_id"])
    
    # ==================== 阶段 7：重建 Rule Version 表 ====================
    
    op.create_table(
        "biz_rule_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column("change_summary", sa.Text(), server_default="", nullable=False),
        sa.Column("snapshot", mysql.JSON(), nullable=False, comment="规则快照"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "version", name="uk_rule_version"),
        sa.ForeignKeyConstraint(["rule_id"], ["biz_rule.id"], name="fk_rule_version_rule", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则版本表"
    )
    
    # ==================== 阶段 8：插入示例数据（可选） ====================
    
    # 创建默认应用
    op.execute("""
        INSERT INTO biz_application (app_key, name, description, app_secret, is_active)
        VALUES ('app_00000000', '示例应用', 'V3 架构示例应用', 'change_me_in_production', 1)
    """)
    
    # 创建默认站点
    op.execute("""
        INSERT INTO biz_site (site_key, app_id, name, domain, alt_domains, access_mode, is_active)
        SELECT 'site_00000000', id, '示例站点', 'localhost', '[]', 'adapter', 1
        FROM biz_application WHERE app_key = 'app_00000000'
    """)


def downgrade() -> None:
    """回滚迁移：删除所有 V3 架构的表。
    
    警告：此操作会丢失所有数据，生产环境慎用！
    """
    op.execute("SET FOREIGN_KEY_CHECKS=0")
    op.execute("DROP TABLE IF EXISTS biz_rule_version")
    op.execute("DROP TABLE IF EXISTS biz_rule_group")
    op.execute("DROP TABLE IF EXISTS biz_rule_site")
    op.execute("DROP TABLE IF EXISTS biz_rule")
    op.execute("DROP TABLE IF EXISTS biz_site")
    op.execute("DROP TABLE IF EXISTS biz_application")
    op.execute("SET FOREIGN_KEY_CHECKS=1")

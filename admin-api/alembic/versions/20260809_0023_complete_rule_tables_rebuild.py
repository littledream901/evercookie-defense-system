"""complete the 20260808_0002 rebuild for biz_rule / biz_rule_site / biz_rule_group

Revision ID: 20260809_0023
Revises: 20260809_0022
Create Date: 2026-08-09

0002 的重建只落地了 biz_application 与 biz_site，biz_rule / biz_rule_site /
biz_rule_group 仍是 0001 时代的旧结构（biz_rule 还带 verdict/mechanism/app_id），
但 alembic_version 已被推进到 0021，所以后续迁移都跳过了这三张表。表结构与 ORM
模型不一致，导致规则、规则组、诊断等接口全部 500。

三张表均为 0 行，按 0002 的目标结构重建，无数据损失。
biz_rule_version 有 6 行历史快照，保持原样不动；只摘掉它指向 biz_rule 的外键，
重建完成后按库中原状恢复（该表现存 6 行本就是孤儿数据，故恢复外键时不做校验）。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '20260809_0023'
down_revision = '20260809_0022'
branch_labels = None
depends_on = None


def upgrade():
    # biz_rule_version 保留数据，仅摘除指向 biz_rule 的外键，避免重建父表时被阻塞
    op.drop_constraint('fk_biz_rule_version_rule', 'biz_rule_version', type_='foreignkey')

    op.execute("SET FOREIGN_KEY_CHECKS=0")
    op.execute("DROP TABLE IF EXISTS biz_rule_site")
    op.execute("DROP TABLE IF EXISTS biz_rule_group")
    op.execute("DROP TABLE IF EXISTS biz_rule")
    op.execute("SET FOREIGN_KEY_CHECKS=1")

    op.create_table(
        "biz_rule",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False, comment="规则名称"),
        sa.Column("description", sa.String(512), server_default="", nullable=False, comment="规则描述"),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False, comment="draft/published/shadow/archived"),
        sa.Column("priority", sa.String(16), server_default="normal", nullable=False, comment="low/normal/high/critical"),
        sa.Column("kind", sa.String(16), server_default="decision", nullable=False, comment="decision/scoring"),
        sa.Column("weight", sa.Integer(), server_default="0", nullable=False, comment="评分权重"),
        sa.Column("disposition_match", mysql.JSON(), nullable=True, comment="命中时的处置动作"),
        sa.Column("disposition_miss", mysql.JSON(), nullable=True, comment="未命中时的处置动作"),
        sa.Column("conditions", mysql.JSON(), nullable=False, comment="规则条件"),
        sa.Column("match_all", sa.Boolean(), server_default="1", nullable=False, comment="是否全部匹配"),
        sa.Column("rule_group", sa.String(64), nullable=True, comment="所属规则组名"),
        sa.Column("tags", mysql.JSON(), nullable=False, comment="标签列表"),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False, comment="版本号"),
        sa.Column("published_at", sa.DateTime(), nullable=True, comment="发布时间"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则表",
    )
    op.create_index("ix_biz_rule_status", "biz_rule", ["status"])

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
        comment="规则-站点关联表",
    )
    op.create_index("ix_biz_rule_site_site", "biz_rule_site", ["site_id"])

    op.create_table(
        "biz_rule_group",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False, comment="所属站点"),
        sa.Column("name", sa.String(64), nullable=False, comment="规则组名称"),
        sa.Column("mode", sa.String(16), server_default="blocklist", nullable=False, comment="blocklist/allowlist"),
        sa.Column("priority", sa.String(16), server_default="normal", nullable=False, comment="优先级"),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False, comment="是否启用"),
        sa.Column("on_no_match", mysql.JSON(), nullable=True, comment="allowlist 组内全未命中时的处置"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "name", name="uk_rule_group_site_name"),
        sa.ForeignKeyConstraint(["site_id"], ["biz_site.id"], name="fk_rule_group_site", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="规则组表",
    )
    op.create_index("idx_rule_group_site", "biz_rule_group", ["site_id"])

    # 恢复 biz_rule_version 的外键。现存 6 行为孤儿（rule_id=1 已不存在），
    # 与迁移前状态一致，故关闭校验以保留数据。
    op.execute("SET FOREIGN_KEY_CHECKS=0")
    op.create_foreign_key(
        'fk_biz_rule_version_rule', 'biz_rule_version', 'biz_rule',
        ['rule_id'], ['id'], ondelete='CASCADE',
    )
    op.execute("SET FOREIGN_KEY_CHECKS=1")


def downgrade():
    # 本迁移用于修补 0002 的部分落地，回滚等于恢复损坏结构，故不实现。
    raise NotImplementedError("0023 是结构修补迁移，不支持回滚；如需还原请用数据库备份")

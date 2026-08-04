"""merge biz_intel_asn_profile into biz_intel_asn

Revision ID: 20260804_0021
Revises: 20260804_0020
Create Date: 2026-08-04

两张 ASN 表的能力是重叠的：``biz_intel_asn_profile`` 除了多一个 ``country``
列，其余字段（asn / operator / network_type / risk_score / is_active / note）
与 ``biz_intel_asn`` 完全同名，gateway 侧的消费逻辑也几乎一致——都覆盖网络
标志、都把 risk_score 推进同一个取最大值的列表。

原设计意图是「情报表管风险、画像表管属性」，但实现上两边都带 risk_score 且
都覆盖 network_type，正交划分没有落地。与其维护两套同构的表、Redis key、
CRUD 与前端页面，不如合并为一张：给 asn 表补上 country 列即可覆盖画像表的
全部能力。

数据迁移策略：以 asn 表为主，画像表的记录按 ASN 号合并进来。
  - ASN 只在画像表存在 → 整行插入 asn 表
  - ASN 两边都有 → 只把 country 补过去，其余字段保留 asn 表的值
    （情报表是风险判定的直接依据，不能被画像数据顶掉）
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0021"
down_revision: Union[str, None] = "20260804_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "biz_intel_asn",
        sa.Column("country", sa.String(8), nullable=False, server_default=""),
    )
    op.create_index("ix_intel_asn_country", "biz_intel_asn", ["country"])

    # 画像表独有的 ASN：整行搬过来
    op.execute(
        """
        INSERT INTO biz_intel_asn
            (asn, operator, network_type, country, risk_score, is_active, note)
        SELECT p.asn, p.operator, p.network_type, p.country,
               p.risk_score, p.is_active, p.note
        FROM biz_intel_asn_profile AS p
        LEFT JOIN biz_intel_asn AS a ON a.asn = p.asn
        WHERE a.asn IS NULL
        """
    )

    # 两边都有的 ASN：只补 country，不动情报表已有的风险字段
    op.execute(
        """
        UPDATE biz_intel_asn AS a
        JOIN biz_intel_asn_profile AS p ON p.asn = a.asn
        SET a.country = p.country
        WHERE a.country = '' AND p.country <> ''
        """
    )

    op.drop_table("biz_intel_asn_profile")


def downgrade() -> None:
    op.create_table(
        "biz_intel_asn_profile",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asn", sa.Integer(), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False, server_default=""),
        sa.Column("network_type", sa.String(32), nullable=False, server_default="DATACENTER"),
        sa.Column("country", sa.String(8), nullable=False, server_default=""),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asn", name="uk_intel_asn_profile_asn"),
    )
    op.create_index("ix_intel_asn_profile_country", "biz_intel_asn_profile", ["country"])

    # 带 country 的记录回填画像表；无法区分原本属于哪张表，故全量复制一份
    op.execute(
        """
        INSERT INTO biz_intel_asn_profile
            (asn, operator, network_type, country, risk_score, is_active, note)
        SELECT asn, operator, network_type, country, risk_score, is_active, note
        FROM biz_intel_asn
        WHERE country <> ''
        """
    )

    op.drop_index("ix_intel_asn_country", table_name="biz_intel_asn")
    op.drop_column("biz_intel_asn", "country")

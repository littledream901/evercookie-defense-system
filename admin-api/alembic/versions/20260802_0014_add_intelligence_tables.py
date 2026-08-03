"""add 6 intelligence tables

Revision ID: 20260802_0014
Revises: 20260802_0013
Create Date: 2026-08-02

补齐管理端「威胁情报」六类维度的存储。此前前端已有完整页面，但后端
``/v2/intelligence`` 全无实现——表、模型、仓储、路由均缺失。

不复用 ``biz_threat_intel``：该表以 ``ip`` 为唯一键，而这六类的主键语义
各不相同（ASN 号 / pattern / finger_id / CIDR），无法共表。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0014"
down_revision: Union[str, None] = "20260802_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = (
    sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
    sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"),
              onupdate=sa.text("NOW()"), nullable=False),
)


def upgrade() -> None:
    op.create_table(
        "biz_intel_asn",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asn", sa.Integer(), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False, server_default=""),
        sa.Column("network_type", sa.String(32), nullable=False, server_default="DATACENTER"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        *_TS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asn", name="uk_intel_asn"),
    )
    op.create_index("ix_intel_asn_active", "biz_intel_asn", ["is_active"])

    op.create_table(
        "biz_intel_crawler",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("feature_type", sa.String(32), nullable=False, server_default="user_agent"),
        sa.Column("pattern", sa.String(256), nullable=False),
        sa.Column("crawler_category", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("crawler_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("is_legitimate", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        *_TS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_type", "pattern", name="uk_intel_crawler_pattern"),
    )
    op.create_index("ix_intel_crawler_category", "biz_intel_crawler", ["crawler_category"])

    op.create_table(
        "biz_intel_fingerprint",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("finger_id", sa.String(128), nullable=False),
        sa.Column("finger_type", sa.String(32), nullable=False, server_default="device"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("canvas_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("webgl_params", sa.String(256), nullable=False, server_default=""),
        sa.Column("audio_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("screen_info", sa.String(64), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        *_TS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finger_id", name="uk_intel_fingerprint_id"),
    )
    op.create_index("ix_intel_fingerprint_type", "biz_intel_fingerprint", ["finger_type"])

    op.create_table(
        "biz_intel_geo_ip",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cidr", sa.String(64), nullable=False),
        sa.Column("country", sa.String(8), nullable=False, server_default=""),
        sa.Column("region", sa.String(64), nullable=False, server_default=""),
        sa.Column("city", sa.String(64), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        *_TS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cidr", name="uk_intel_geo_ip_cidr"),
    )
    op.create_index("ix_intel_geo_ip_country", "biz_intel_geo_ip", ["country"])

    op.create_table(
        "biz_intel_ip_profile",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cidr", sa.String(64), nullable=False),
        sa.Column("network_type", sa.String(32), nullable=False, server_default="DATACENTER"),
        sa.Column("is_vpn", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_proxy", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_tor", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(512), nullable=False, server_default=""),
        *_TS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cidr", name="uk_intel_ip_profile_cidr"),
    )
    op.create_index("ix_intel_ip_profile_active", "biz_intel_ip_profile", ["is_active"])

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
        *_TS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asn", name="uk_intel_asn_profile_asn"),
    )
    op.create_index("ix_intel_asn_profile_country", "biz_intel_asn_profile", ["country"])


def downgrade() -> None:
    for table in (
        "biz_intel_asn_profile",
        "biz_intel_ip_profile",
        "biz_intel_geo_ip",
        "biz_intel_fingerprint",
        "biz_intel_crawler",
        "biz_intel_asn",
    ):
        op.drop_table(table)

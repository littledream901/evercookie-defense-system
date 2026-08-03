"""B--: add (is_active, note) index on biz_intel_ip_profile.

Revision ID: 20260803_0018
Revises: 20260802_0017
Create Date: 2026-08-03

GET /v2/intelligence/ip_profile/external-sources 按 ``note LIKE 'external:<id>%'``
逐源统计条目数。外部源单次可导入上万条网段，无索引时每次统计都是全表扫描。
note 是 VARCHAR(512)，只对前 64 字符建前缀索引：源标记形如 ``external:aws``，
64 字符足够区分，同时避免全列索引占用过多空间。
"""
from __future__ import annotations

from alembic import op

revision = "20260803_0018"
down_revision = "20260802_0017"
branch_labels = None
depends_on = None

_INDEX = "ix_intel_ip_profile_active_note"
_TABLE = "biz_intel_ip_profile"


def upgrade() -> None:
    op.create_index(
        _INDEX,
        _TABLE,
        ["is_active", "note"],
        mysql_length={"note": 64},
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)

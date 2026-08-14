"""add_pipeline_config_columns

Revision ID: f81ad9de54ea
Revises: 20260814_0005
Create Date: 2026-08-14 22:50:01.518211

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f81ad9de54ea'
down_revision: Union[str, None] = '20260814_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """向 biz_default_disposition 表添加流水线各阶段开关字段。"""
    op.add_column(
        'biz_default_disposition',
        sa.Column('whitelist_enabled', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.add_column(
        'biz_default_disposition',
        sa.Column('clock_enabled', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.add_column(
        'biz_default_disposition',
        sa.Column('threat_intel_enabled', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.add_column(
        'biz_default_disposition',
        sa.Column('security_enabled', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.add_column(
        'biz_default_disposition',
        sa.Column('rules_enabled', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.add_column(
        'biz_default_disposition',
        sa.Column('scoring_enabled', sa.Boolean(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    """回滚：删除流水线开关字段。"""
    op.drop_column('biz_default_disposition', 'scoring_enabled')
    op.drop_column('biz_default_disposition', 'rules_enabled')
    op.drop_column('biz_default_disposition', 'security_enabled')
    op.drop_column('biz_default_disposition', 'threat_intel_enabled')
    op.drop_column('biz_default_disposition', 'clock_enabled')
    op.drop_column('biz_default_disposition', 'whitelist_enabled')

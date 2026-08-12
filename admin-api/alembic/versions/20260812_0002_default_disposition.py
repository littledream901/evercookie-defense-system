"""default disposition table

Revision ID: 20260812_0002
Revises: 20260809_0001
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '20260812_0002'
down_revision: Union[str, None] = '20260809_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # biz_default_disposition - 默认处置表（决策流水线 default 阶段兜底）
    op.create_table(
        'biz_default_disposition',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.BigInteger(), nullable=False),
        sa.Column('disposition', mysql.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', name='uk_default_disposition_site'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )


def downgrade() -> None:
    op.drop_table('biz_default_disposition')

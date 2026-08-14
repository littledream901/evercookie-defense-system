"""drop rule kind weight

Revision ID: 20260814_0004
Revises: 20260814_0003
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260814_0004'
down_revision: Union[str, None] = '20260814_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 规则统一为决策规则，打分能力已收敛到 biz_scoring_config；
    # 删除 biz_rule 上遗留的 kind/weight 两列。
    op.drop_column('biz_rule', 'weight')
    op.drop_column('biz_rule', 'kind')


def downgrade() -> None:
    op.add_column(
        'biz_rule',
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='decision'),
    )
    op.add_column(
        'biz_rule',
        sa.Column('weight', sa.Integer(), nullable=False, server_default='0'),
    )

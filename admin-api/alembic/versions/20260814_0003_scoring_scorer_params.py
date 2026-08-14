"""scoring config scorer_params

Revision ID: 20260814_0003
Revises: 20260812_0002
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '20260814_0003'
down_revision: Union[str, None] = '20260812_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # biz_scoring_config 增加 scorer_params，承载各 scorer 的默认评分常量覆盖。
    op.add_column(
        'biz_scoring_config',
        sa.Column(
            'scorer_params',
            mysql.JSON(),
            nullable=False,
            server_default=sa.text("(JSON_OBJECT())"),
        ),
    )


def downgrade() -> None:
    op.drop_column('biz_scoring_config', 'scorer_params')

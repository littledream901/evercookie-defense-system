"""追加 must_change_password 字段

Revision ID: 20260731_0004
Revises: 20260731_0003
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260731_0004"
down_revision: Union[str, None] = "20260731_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_user",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
            comment="首次登录必须修改密码",
        ),
    )


def downgrade() -> None:
    op.drop_column("sys_user", "must_change_password")

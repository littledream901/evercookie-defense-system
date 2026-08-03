"""add app_secret to biz_application

Revision ID: 20260801_0008
Revises: 20260801_0007
Create Date: 2026-08-01

为存量应用回填随机密钥
----------------------
新列非空且无业务默认值。若留空串，开启 ``signature_required`` 后这些应用会
直接失败关闭（网关拒绝无密钥凭据），等于停服。因此这里为每行生成独立的随机
密钥：MySQL 侧用 ``SHA2(CONCAT(UUID(), RAND()), 256)`` 逐行求值，保证不同
应用不会共用同一密钥。回填后需由运维通过后台「轮换密钥」把密钥告知接入方。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0008"
down_revision: Union[str, None] = "20260801_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "biz_application",
        sa.Column("app_secret", sa.String(length=64), nullable=False, server_default=""),
    )
    op.execute(
        "UPDATE biz_application "
        "SET app_secret = LEFT(SHA2(CONCAT(UUID(), RAND(), id), 256), 48) "
        "WHERE app_secret = '' OR app_secret IS NULL"
    )


def downgrade() -> None:
    op.drop_column("biz_application", "app_secret")

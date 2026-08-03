"""add biz_scoring_config; allow app_id=0 global sentinel

Revision ID: 20260802_0013
Revises: 20260802_0012
Create Date: 2026-08-02

两件事：

1. 补建 ``biz_scoring_config``。模型早已定义，但从未进入任何迁移，
   导致 ``GET /v2/scoring/global`` 报 1146 Table doesn't exist。

2. 解除 scoring / clock_limits / page_resource 三张表指向
   ``biz_application.id`` 的外键。全局配置以 ``app_id = 0`` 作哨兵值，
   而 0 不是合法站点主键，保留外键会让全局写入直接违约。

哨兵值选 0 而非 NULL：MySQL 唯一索引不约束 NULL，用 NULL 会让全局记录
每次 UPSERT 都新插一行，破坏「全局配置唯一」的语义。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0013"
down_revision: Union[str, None] = "20260802_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "biz_scoring_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("threshold_suspect", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("threshold_hostile", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("disposition_suspect", sa.JSON(), nullable=True),
        sa.Column("disposition_hostile", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"),
                  onupdate=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", name="uk_scoring_config_app"),
    )

    # 解除外键：app_id=0 是全局哨兵，不对应真实站点。
    # biz_clock_limits 在模型里声明了 ForeignKey 但库中从未建出，无需处理。
    op.drop_constraint("biz_page_resource_ibfk_1", "biz_page_resource", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "biz_page_resource_ibfk_1", "biz_page_resource", "biz_application",
        ["app_id"], ["id"],
    )
    op.drop_table("biz_scoring_config")

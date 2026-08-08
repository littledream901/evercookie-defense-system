"""rename scoring app_id to site_id

Revision ID: 20260809_0020
Revises: 20260808_0002
Create Date: 2026-08-09
"""
from alembic import op

revision = '20260809_0020'
down_revision = '20260808_0002'
branch_labels = None
depends_on = None

def upgrade():
    # 重命名列（唯一约束 uk_scoring_config_app 会自动跟随）
    op.execute("ALTER TABLE biz_scoring_config CHANGE COLUMN app_id site_id BIGINT NOT NULL")

def downgrade():
    op.execute("ALTER TABLE biz_scoring_config CHANGE COLUMN site_id app_id BIGINT NOT NULL")

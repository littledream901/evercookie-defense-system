"""rename page_resource app_id to site_id

Revision ID: 20260809_0022
Revises: 20260809_0021
Create Date: 2026-08-09

biz_page_resource 未随 0012 的 rule 表一起改名，模型已用 site_id 而库里仍是 app_id，
导致所有页面资源接口 500。表上无外键（app_id 允许 0 作为全局哨兵值），故只需处理
唯一约束与二级索引。
"""
from alembic import op

revision = '20260809_0022'
down_revision = '20260809_0021'
branch_labels = None
depends_on = None


def upgrade():
    # 唯一约束与二级索引都以 app_id 为首列，重命名前必须先摘掉
    op.drop_index('ix_page_resource_app_enabled', table_name='biz_page_resource')
    op.drop_constraint('uk_page_resource_app_name', 'biz_page_resource', type_='unique')

    op.execute("ALTER TABLE biz_page_resource CHANGE COLUMN app_id site_id BIGINT NOT NULL")

    op.create_unique_constraint('uk_page_resource_site_name', 'biz_page_resource', ['site_id', 'name'])
    op.create_index('ix_page_resource_site_enabled', 'biz_page_resource', ['site_id', 'enabled'])


def downgrade():
    op.drop_index('ix_page_resource_site_enabled', table_name='biz_page_resource')
    op.drop_constraint('uk_page_resource_site_name', 'biz_page_resource', type_='unique')

    op.execute("ALTER TABLE biz_page_resource CHANGE COLUMN site_id app_id BIGINT NOT NULL")

    op.create_unique_constraint('uk_page_resource_app_name', 'biz_page_resource', ['app_id', 'name'])
    op.create_index('ix_page_resource_app_enabled', 'biz_page_resource', ['app_id', 'enabled'])

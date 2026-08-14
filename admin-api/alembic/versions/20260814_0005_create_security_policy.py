"""创建安全策略配置表

Revision ID: 20260814_0005
Revises: 20260814_0004
Create Date: 2026-08-14

"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '20260814_0005'
down_revision: Union[str, None] = '20260814_0004'
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    """创建 biz_security_policy 表。"""
    op.create_table(
        'biz_security_policy',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        
        # 威胁情报配置
        sa.Column('threat_intel_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('threat_intel_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('threat_intel_score', sa.Integer(), nullable=False, server_default='100'),
        
        # 扫描器配置
        sa.Column('scanner_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('scanner_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('scanner_score', sa.Integer(), nullable=False, server_default='80'),
        
        # VPN+数据中心配置
        sa.Column('vpn_datacenter_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('vpn_datacenter_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('vpn_datacenter_score', sa.Integer(), nullable=False, server_default='60'),
        
        # Tor 检测配置
        sa.Column('tor_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('tor_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('tor_score', sa.Integer(), nullable=False, server_default='90'),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', name='uk_security_policy_site'),
        sa.ForeignKeyConstraint(['site_id'], ['biz_site.id'], name='fk_security_policy_site', ondelete='CASCADE'),
        
        mysql_charset='utf8mb4',
        comment='安全策略配置'
    )


def downgrade() -> None:
    """删除 biz_security_policy 表。"""
    op.drop_table('biz_security_policy')

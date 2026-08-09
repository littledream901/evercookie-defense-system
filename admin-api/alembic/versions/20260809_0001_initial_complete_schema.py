"""Initial complete schema

Revision ID: 20260809_0001
Revises: 
Create Date: 2026-08-09 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '20260809_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========================================
    # 系统表（RBAC）
    # ========================================
    
    # sys_user - 用户表
    op.create_table(
        'sys_user',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(64), nullable=False),
        sa.Column('email', sa.String(128), nullable=False),
        sa.Column('display_name', sa.String(128), nullable=False, server_default=''),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_sys_user_username'),
        sa.UniqueConstraint('email', name='uq_sys_user_email'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_sys_user_status', 'sys_user', ['status'])
    
    # sys_role - 角色表
    op.create_table(
        'sys_role',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('description', sa.String(255), nullable=False, server_default=''),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_sys_role_name'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    
    # sys_permission - 权限表
    op.create_table(
        'sys_permission',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(128), nullable=False),
        sa.Column('description', sa.String(255), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_sys_permission_code'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    
    # sys_user_role - 用户角色关联表
    op.create_table(
        'sys_user_role',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['sys_user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['sys_role.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'role_id', name='uk_user_role'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_sys_user_role_user', 'sys_user_role', ['user_id'])
    op.create_index('ix_sys_user_role_role', 'sys_user_role', ['role_id'])
    
    # sys_role_permission - 角色权限关联表
    op.create_table(
        'sys_role_permission',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('permission_code', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['role_id'], ['sys_role.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('role_id', 'permission_code', name='uk_role_permission'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_sys_role_permission_role', 'sys_role_permission', ['role_id'])
    
    # sys_user_api_key - 用户 API Key 表
    op.create_table(
        'sys_user_api_key',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('key_prefix', sa.String(16), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['sys_user.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('key_hash', name='uq_sys_user_api_key_hash'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('idx_user_api_key_user', 'sys_user_api_key', ['user_id'])
    op.create_index('idx_user_api_key_key_hash', 'sys_user_api_key', ['key_hash'])
    
    # sys_audit_log - 审计日志表
    op.create_table(
        'sys_audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('username', sa.String(64), nullable=False, server_default=''),
        sa.Column('method', sa.String(16), nullable=False, server_default=''),
        sa.Column('path', sa.String(512), nullable=False, server_default=''),
        sa.Column('resource', sa.String(64), nullable=False, server_default=''),
        sa.Column('resource_id', sa.String(128), nullable=False, server_default=''),
        sa.Column('action', sa.String(32), nullable=False, server_default=''),
        sa.Column('status_code', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ip', sa.String(64), nullable=False, server_default=''),
        sa.Column('user_agent', sa.String(512), nullable=False, server_default=''),
        sa.Column('request_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('detail', mysql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('idx_audit_occurred', 'sys_audit_log', ['occurred_at'])
    op.create_index('idx_audit_user', 'sys_audit_log', ['user_id', 'occurred_at'])
    op.create_index('idx_audit_resource', 'sys_audit_log', ['resource', 'occurred_at'])
    
    # ========================================
    # 业务表（V3 两层架构）
    # ========================================
    
    # biz_application - 应用表
    op.create_table(
        'biz_application',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('app_key', sa.String(32), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.String(512), nullable=False, server_default=''),
        sa.Column('owner_user_id', sa.BigInteger(), nullable=True),
        sa.Column('app_secret', sa.String(128), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('app_key', name='uq_biz_application_app_key'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_biz_application_active', 'biz_application', ['is_active'])
    
    # biz_site - 站点表
    op.create_table(
        'biz_site',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_key', sa.String(32), nullable=False),
        sa.Column('app_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('domain', sa.String(512), nullable=False),
        sa.Column('alt_domains', mysql.JSON(), nullable=False),
        sa.Column('access_mode', sa.String(16), nullable=False, server_default='adapter'),
        sa.Column('site_secret', sa.String(128), nullable=False, server_default=''),
        sa.Column('sdk_version', sa.String(16), nullable=True),
        sa.Column('gateway_url', sa.String(512), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('clock_stats_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('log_retention_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['app_id'], ['biz_application.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('site_key', name='uq_biz_site_site_key'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_biz_site_app', 'biz_site', ['app_id'])
    op.create_index('ix_biz_site_active', 'biz_site', ['is_active'])
    
    # biz_rule - 规则表
    op.create_table(
        'biz_rule',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.String(512), nullable=False, server_default=''),
        sa.Column('status', sa.String(16), nullable=False, server_default='draft'),
        sa.Column('priority', sa.String(16), nullable=False, server_default='normal'),
        sa.Column('kind', sa.String(16), nullable=False, server_default='decision'),
        sa.Column('weight', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('disposition_match', mysql.JSON(), nullable=True),
        sa.Column('disposition_miss', mysql.JSON(), nullable=True),
        sa.Column('conditions', mysql.JSON(), nullable=False),
        sa.Column('match_all', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('rule_group', sa.String(64), nullable=True),
        sa.Column('tags', mysql.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_biz_rule_status', 'biz_rule', ['status'])
    
    # biz_rule_site - 规则站点关联表
    op.create_table(
        'biz_rule_site',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.BigInteger(), nullable=False),
        sa.Column('site_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['rule_id'], ['biz_rule.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['biz_site.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('rule_id', 'site_id', name='uk_rule_site'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_biz_rule_site_site', 'biz_rule_site', ['site_id'])
    
    # biz_rule_group - 规则组表
    op.create_table(
        'biz_rule_group',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('mode', sa.String(16), nullable=False, server_default='blocklist'),
        sa.Column('priority', sa.String(16), nullable=False, server_default='normal'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('on_no_match', mysql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['site_id'], ['biz_site.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('site_id', 'name', name='uk_rule_group_site_name'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    
    # biz_rule_version - 规则版本表
    op.create_table(
        'biz_rule_version',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.BigInteger(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.BigInteger(), nullable=True),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('snapshot', mysql.JSON(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['rule_id'], ['biz_rule.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('rule_id', 'version', name='uk_rule_version'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    
    # ========================================
    # 其他业务表
    # ========================================
    
    # biz_scoring_config - 评分配置表
    op.create_table(
        'biz_scoring_config',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(128), nullable=False, server_default=''),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('threshold_suspect', sa.Integer(), nullable=False, server_default='40'),
        sa.Column('threshold_hostile', sa.Integer(), nullable=False, server_default='70'),
        sa.Column('weights', mysql.JSON(), nullable=False),
        sa.Column('disposition_suspect', mysql.JSON(), nullable=True),
        sa.Column('disposition_hostile', mysql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', name='uk_scoring_config_app'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    
    # biz_clock_limits - 频控配置表
    op.create_table(
        'biz_clock_limits',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.BigInteger(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('windows', mysql.JSON(), nullable=False),
        sa.Column('ban_seconds', sa.Integer(), nullable=False, server_default='900'),
        sa.Column('ban_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', name='uk_clock_limits_site'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    
    # biz_page_resource - 页面资源表
    op.create_table(
        'biz_page_resource',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False, server_default='safe'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(64), nullable=False, server_default='text/html; charset=utf-8'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', 'name', name='uk_page_resource_site_name'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_page_resource_site_enabled', 'biz_page_resource', ['site_id', 'enabled'])
    
    # ========================================
    # 威胁情报表
    # ========================================
    
    # biz_threat_intel - 威胁情报IP表
    op.create_table(
        'biz_threat_intel',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ip', sa.String(64), nullable=False),
        sa.Column('category', sa.String(32), nullable=False, server_default='malicious'),
        sa.Column('severity', sa.String(16), nullable=False, server_default='medium'),
        sa.Column('source', sa.String(64), nullable=False, server_default='manual'),
        sa.Column('confidence', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('description', sa.String(512), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('extra', mysql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip', name='uk_threat_intel_ip'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_threat_intel_category', 'biz_threat_intel', ['category'])
    op.create_index('ix_threat_intel_source', 'biz_threat_intel', ['source'])
    
    # biz_intel_asn - ASN情报表
    op.create_table(
        'biz_intel_asn',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('asn', sa.Integer(), nullable=False),
        sa.Column('operator', sa.String(128), nullable=False, server_default=''),
        sa.Column('network_type', sa.String(32), nullable=False, server_default='DATACENTER'),
        sa.Column('country', sa.String(8), nullable=False, server_default=''),
        sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('note', sa.String(512), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asn', name='uk_intel_asn'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_intel_asn_active', 'biz_intel_asn', ['is_active'])
    op.create_index('ix_intel_asn_country', 'biz_intel_asn', ['country'])
    
    # biz_intel_crawler - 爬虫情报表
    op.create_table(
        'biz_intel_crawler',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('feature_type', sa.String(32), nullable=False, server_default='user_agent'),
        sa.Column('pattern', sa.String(256), nullable=False),
        sa.Column('crawler_category', sa.String(32), nullable=False, server_default='unknown'),
        sa.Column('crawler_name', sa.String(128), nullable=False, server_default=''),
        sa.Column('is_legitimate', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('note', sa.String(512), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('feature_type', 'pattern', name='uk_intel_crawler_pattern'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_intel_crawler_category', 'biz_intel_crawler', ['crawler_category'])
    
    # biz_intel_fingerprint - 指纹情报表
    op.create_table(
        'biz_intel_fingerprint',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('finger_id', sa.String(128), nullable=False),
        sa.Column('finger_type', sa.String(32), nullable=False, server_default='device'),
        sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source', sa.String(64), nullable=False, server_default='manual'),
        sa.Column('canvas_hash', sa.String(128), nullable=False, server_default=''),
        sa.Column('webgl_params', sa.String(256), nullable=False, server_default=''),
        sa.Column('audio_hash', sa.String(128), nullable=False, server_default=''),
        sa.Column('screen_info', sa.String(64), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('note', sa.String(512), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('finger_id', name='uk_intel_fingerprint_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_intel_fingerprint_type', 'biz_intel_fingerprint', ['finger_type'])
    
    # biz_intel_geo_ip - GeoIP情报表
    op.create_table(
        'biz_intel_geo_ip',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('cidr', sa.String(64), nullable=False),
        sa.Column('country', sa.String(8), nullable=False, server_default=''),
        sa.Column('region', sa.String(64), nullable=False, server_default=''),
        sa.Column('city', sa.String(64), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('note', sa.String(512), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cidr', name='uk_intel_geo_ip_cidr'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_intel_geo_ip_country', 'biz_intel_geo_ip', ['country'])
    
    # biz_intel_ip_profile - IP画像情报表
    op.create_table(
        'biz_intel_ip_profile',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('cidr', sa.String(64), nullable=False),
        sa.Column('network_type', sa.String(32), nullable=False, server_default='DATACENTER'),
        sa.Column('is_vpn', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_proxy', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_tor', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('note', sa.String(512), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cidr', name='uk_intel_ip_profile_cidr'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_intel_ip_profile_active', 'biz_intel_ip_profile', ['is_active'])
    op.create_index('ix_intel_ip_profile_active_note', 'biz_intel_ip_profile', ['is_active', 'note'], mysql_length={'note': 64})


def downgrade() -> None:
    # ========================================
    # 删除所有表（逆序删除，先删除依赖表）
    # ========================================
    
    # 威胁情报表
    op.drop_table('biz_intel_ip_profile')
    op.drop_table('biz_intel_geo_ip')
    op.drop_table('biz_intel_fingerprint')
    op.drop_table('biz_intel_crawler')
    op.drop_table('biz_intel_asn')
    op.drop_table('biz_threat_intel')
    
    # 其他业务表
    op.drop_table('biz_page_resource')
    op.drop_table('biz_clock_limits')
    op.drop_table('biz_scoring_config')
    
    # 规则相关表
    op.drop_table('biz_rule_version')
    op.drop_table('biz_rule_group')
    op.drop_table('biz_rule_site')
    op.drop_table('biz_rule')
    
    # 站点和应用表
    op.drop_table('biz_site')
    op.drop_table('biz_application')
    
    # 系统表
    op.drop_table('sys_audit_log')
    op.drop_table('sys_user_api_key')
    op.drop_table('sys_role_permission')
    op.drop_table('sys_user_role')
    op.drop_table('sys_permission')
    op.drop_table('sys_role')
    op.drop_table('sys_user')


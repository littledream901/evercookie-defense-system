"""SQLAlchemy ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from fangyu_shared.utils.time import utcnow
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserModel(Base, TimestampMixin):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default="1", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    roles: Mapped[list["UserRoleModel"]] = relationship(back_populates="user", lazy="selectin")


class RoleModel(Base, TimestampMixin):
    __tablename__ = "sys_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list["RolePermissionModel"]] = relationship(
        back_populates="role", lazy="selectin"
    )


class PermissionModel(Base, TimestampMixin):
    __tablename__ = "sys_permission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")


class UserRoleModel(Base, TimestampMixin):
    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uk_user_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_role.id"), nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="roles")
    role: Mapped[RoleModel] = relationship(lazy="selectin")


class RolePermissionModel(Base, TimestampMixin):
    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_code", name="uk_role_permission"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_role.id"), nullable=False)
    permission_code: Mapped[str] = mapped_column(String(128), nullable=False)

    role: Mapped[RoleModel] = relationship(back_populates="permissions")


class ApplicationModel(Base, TimestampMixin):
    __tablename__ = "biz_application"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    """站点唯一标识，格式 site_<hex8>，同时作为 X-App-Key（API Key）。"""
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(512), nullable=False)
    """主域名，创建后不可修改，用作站点业务标识。"""
    alt_domains: Mapped[list[str]] = mapped_column(MySQLJSON, default=list, nullable=False)
    access_mode: Mapped[str] = mapped_column(String(16), default="adapter", nullable=False)
    """接入模式：cloud（云端转发）/ sdk（SDK接入）。"""
    app_secret: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    """HMAC 验签密钥，仅创建/轮换时返回一次。"""
    sdk_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gateway_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """站点专属网关地址；留空则用部署级默认网关（前端从环境变量读取）。"""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    clock_stats_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    log_retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class RuleSiteModel(Base):
    """规则 ↔ 站点关联表（多对多）。

    一条规则可被多个站点复用；一个站点可绑定多条规则。
    发布时按此表把规则写入每个站点的 Redis 分片 fangyu:rules:{site_id}。
    """

    __tablename__ = "biz_rule_site"
    __table_args__ = (
        UniqueConstraint("rule_id", "site_id", name="uk_rule_site"),
        Index("ix_biz_rule_site_site", "site_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("biz_rule.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("biz_application.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RuleModel(Base, TimestampMixin):
    __tablename__ = "biz_rule"
    __table_args__ = (
        Index("ix_biz_rule_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="decision", nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disposition_match: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)
    """命中条件时的处置动作（mechanism/target/challengeKind/ttlSeconds）。"""
    disposition_miss: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)
    """未命中条件时的处置动作，默认 pass 继续执行后续规则。"""
    conditions: Mapped[list[dict]] = mapped_column(MySQLJSON, default=list)
    match_all: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rule_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """所属规则组名，对应 biz_rule_group.name。"""
    tags: Mapped[list[str]] = mapped_column(MySQLJSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RuleGroupModel(Base, TimestampMixin):
    """规则组：为一批决策规则提供共享作用域与兜底处置。"""

    __tablename__ = "biz_rule_group"
    __table_args__ = (
        UniqueConstraint("site_id", "name", name="uk_rule_group_site_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("biz_application.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="blocklist", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    on_no_match: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)
    """allowlist 模式下组内全未命中时施加的处置。"""


class RuleVersionModel(Base, TimestampMixin):
    __tablename__ = "biz_rule_version"
    __table_args__ = (
        UniqueConstraint("rule_id", "version", name="uk_rule_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("biz_rule.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    change_summary: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict] = mapped_column(MySQLJSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ThreatIntelModel(Base, TimestampMixin):
    __tablename__ = "biz_threat_intel"
    __table_args__ = (
        UniqueConstraint("ip", name="uk_threat_intel_ip"),
        Index("ix_threat_intel_category", "category"),
        Index("ix_threat_intel_source", "source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="malicious", nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extra: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)


class AsnIntelModel(Base, TimestampMixin):
    """ASN 情报：按自治域号标注运营商类型、国别与风险。

    与 GeoLite2-ASN.mmdb 的关系是「覆盖」而非「替代」：MMDB 提供 asn 与
    asn_org 的事实解析，本表提供人工维护的 network_type / country / risk_score，
    决策时以本表为准。

    合并了原 ``AsnProfileIntelModel``：两者字段高度重叠，画像表只多一个 country，
    其余行为与情报表完全一致。现在统一由此表承载。
    """

    __tablename__ = "biz_intel_asn"
    __table_args__ = (
        UniqueConstraint("asn", name="uk_intel_asn"),
        Index("ix_intel_asn_active", "is_active"),
        Index("ix_intel_asn_country", "country"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asn: Mapped[int] = mapped_column(Integer, nullable=False)
    operator: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    network_type: Mapped[str] = mapped_column(String(32), default="DATACENTER", nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(String(512), default="")


class CrawlerIntelModel(Base, TimestampMixin):
    """爬虫特征情报：按 UA / Header 等特征串识别爬虫。

    ``is_legitimate`` 区分搜索引擎正规爬虫与恶意采集器——前者通常放行，
    后者按 risk_score 参与评分。
    """

    __tablename__ = "biz_intel_crawler"
    __table_args__ = (
        UniqueConstraint("feature_type", "pattern", name="uk_intel_crawler_pattern"),
        Index("ix_intel_crawler_category", "crawler_category"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feature_type: Mapped[str] = mapped_column(String(32), default="user_agent", nullable=False)
    pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    crawler_category: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    crawler_name: Mapped[str] = mapped_column(String(128), default="")
    is_legitimate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(String(512), default="")


class FingerprintIntelModel(Base, TimestampMixin):
    """设备指纹情报：已知的自动化工具 / 农场设备指纹。

    ``hit_count`` 预留用于统计命中次数，当前版本暂未实现自动累加，
    可用于手工标注高频指纹。
    """

    __tablename__ = "biz_intel_fingerprint"
    __table_args__ = (
        UniqueConstraint("finger_id", name="uk_intel_fingerprint_id"),
        Index("ix_intel_fingerprint_type", "finger_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    finger_id: Mapped[str] = mapped_column(String(128), nullable=False)
    finger_type: Mapped[str] = mapped_column(String(32), default="device", nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    canvas_hash: Mapped[str] = mapped_column(String(128), default="")
    webgl_params: Mapped[str] = mapped_column(String(256), default="")
    audio_hash: Mapped[str] = mapped_column(String(128), default="")
    screen_info: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(String(512), default="")


class GeoIpIntelModel(Base, TimestampMixin):
    """GeoIP 手工覆盖：按 CIDR 纠正 MMDB 的地理归属。

    MMDB 的国家判定偶有偏差（尤其是新分配段与 anycast），本表提供人工覆盖，
    决策时优先于 MMDB 结果。
    """

    __tablename__ = "biz_intel_geo_ip"
    __table_args__ = (
        UniqueConstraint("cidr", name="uk_intel_geo_ip_cidr"),
        Index("ix_intel_geo_ip_country", "country"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cidr: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    region: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(String(512), default="")


class IpProfileIntelModel(Base, TimestampMixin):
    """IP 网段画像：按 CIDR 标注代理 / VPN / Tor 属性。

    与 ``fangyu:profile:ip:*`` 的运行时画像不同，本表是按网段维护的静态情报，
    覆盖面更广且不依赖历史流量。
    """

    __tablename__ = "biz_intel_ip_profile"
    __table_args__ = (
        UniqueConstraint("cidr", name="uk_intel_ip_profile_cidr"),
        Index("ix_intel_ip_profile_active", "is_active"),
        # 外部源按 note 前缀（``external:<源 id>``）统计各源贡献量，
        # note 只取前 64 字符建前缀索引，足够区分源标记且避免 512 字符全列索引。
        Index(
            "ix_intel_ip_profile_active_note",
            "is_active",
            "note",
            mysql_length={"note": 64},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cidr: Mapped[str] = mapped_column(String(64), nullable=False)
    network_type: Mapped[str] = mapped_column(String(32), default="DATACENTER", nullable=False)
    is_vpn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_proxy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(String(512), default="")


class ClockLimitsModel(Base, TimestampMixin):
    """站点级频控阈值。

    以 MySQL 为真相、Redis 为 gateway 读取面。不做成纯 Redis 是因为频控阈值
    是安全配置：Redis flush 后若无处可恢复，站点收紧过的阈值会静默退回宽松
    默认值，而运维不会收到任何提示。

    ``windows`` 存 ``{窗口名: 阈值}``，缺省窗口由 gateway 回退到
    :data:`fangyu_shared.clock.limits.DEFAULT_LIMITS`，因此站点只需覆盖关心的那档。
    """

    __tablename__ = "biz_clock_limits"
    __table_args__ = (UniqueConstraint("app_id", name="uk_clock_limits_app"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    """站点 ID；``0`` 为全局配置哨兵值，故不设外键。"""
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    windows: Mapped[dict] = mapped_column(MySQLJSON, default=dict, nullable=False)
    ban_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    ban_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PageResourceModel(Base, TimestampMixin):
    """页面资源：serve_alt 机制的内容来源。

    admin 在此维护「安全页」和「落地页」的 HTML 片段，保存后同步到
    Redis ``fangyu:page_resources:{app_id}``，gateway serve_alt 命中时
    按 ``target.url``（资源名）取出内容直接回传给 adapter。
    """

    __tablename__ = "biz_page_resource"
    __table_args__ = (
        UniqueConstraint("app_id", "name", name="uk_page_resource_app_name"),
        Index("ix_page_resource_app_enabled", "app_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    """站点 ID；``0`` 为全局资源哨兵值，故不设外键。"""
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    """资源标识符，对应 serve_alt(page=...) 的 page 参数。"""
    kind: Mapped[str] = mapped_column(String(16), default="safe", nullable=False)
    """safe | landing。safe 投给可信访客，landing 投给嫌疑访客。"""
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    """页面 HTML 内容（含内联脚本）。"""
    content_type: Mapped[str] = mapped_column(String(64), default="text/html; charset=utf-8", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ScoringConfigModel(Base, TimestampMixin):
    """站点评分配置。

    每个站点对应唯一一条记录（UPSERT 语义）。
    ``weights`` 存 {维度key: 权重0-100}，缺失维度由 gateway 回退到默认权重。
    ``disposition_suspect`` / ``disposition_hostile`` 为 JSON，null 表示沿用规则链默认处置。
    """

    __tablename__ = "biz_scoring_config"
    __table_args__ = (
        UniqueConstraint("app_id", name="uk_scoring_config_app"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    """站点 ID；``0`` 为全局配置哨兵值，故不设外键。"""
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    threshold_suspect: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    threshold_hostile: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    weights: Mapped[dict] = mapped_column(MySQLJSON, default=dict, nullable=False)
    disposition_suspect: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)
    disposition_hostile: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "sys_audit_log"
    __table_args__ = (
        Index("idx_audit_occurred", "occurred_at"),
        Index("idx_audit_user", "user_id", "occurred_at"),
        Index("idx_audit_resource", "resource", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    method: Mapped[str] = mapped_column(String(16), default="")
    path: Mapped[str] = mapped_column(String(512), default="")
    resource: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(32), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)

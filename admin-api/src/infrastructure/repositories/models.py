"""SQLAlchemy ORM 模型。"""

from __future__ import annotations

from datetime import datetime

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
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id"))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    domains: Mapped[list[str]] = mapped_column(MySQLJSON, default=list)


class RuleModel(Base, TimestampMixin):
    __tablename__ = "biz_rule"
    __table_args__ = (
        Index("ix_biz_rule_app_status", "app_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("biz_application.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="decision", nullable=False)
    """规则种类：decision（命中即终止）/ scoring（仅贡献权重）。"""
    weight: Mapped[int] = mapped_column(Integer, default=0)
    """仅 kind=scoring 时有意义。"""
    disposition: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)
    """处置三层结构（verdict/mechanism/target），仅 kind=decision 时非空。"""
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
        UniqueConstraint("app_id", "name", name="uk_rule_group_app_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("biz_application.id"), nullable=False)
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
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    windows: Mapped[dict] = mapped_column(MySQLJSON, default=dict, nullable=False)
    ban_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    ban_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


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

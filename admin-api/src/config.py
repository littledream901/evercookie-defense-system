"""Admin API 配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ADMIN_",
        extra="ignore",
    )

    service_name: str = "admin-api"
    version: str = "2.0.0"
    host: str = "0.0.0.0"
    port: int = 8081
    workers: int = 2
    log_level: str = "INFO"
    log_format: str = "json"

    # Database
    database_url: str = "mysql+aiomysql://fangyu:fangyu@localhost:3306/fangyu"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_recycle: int = 3600

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50

    # ClickHouse
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_database: str = "fangyu"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""

    # JWT
    jwt_secret: str = Field(default="please-change-me", min_length=8)
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 7200
    jwt_refresh_ttl_seconds: int = 604800

    # Permission cache
    permission_cache_ttl: int = 300

    # App Key Redis 映射
    app_key_redis_prefix: str = "fangyu:app_keys:"
    app_key_redis_ttl_seconds: int = 0  # 0 表示永久缓存，由 admin 侧显式清除

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True

    # Rate limiter
    login_rate_limit_per_minute: int = 10


_settings: AdminSettings | None = None


def get_settings() -> AdminSettings:
    global _settings
    if _settings is None:
        _settings = AdminSettings()
    return _settings

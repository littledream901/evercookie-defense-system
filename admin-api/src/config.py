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
    # 无默认值：内置弱口令的连接串会在忘记配置 ADMIN_DATABASE_URL 时静默生效，
    # 让服务连上一个非预期的库。缺失时直接启动失败更安全。
    database_url: str
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
    # 无默认值且长度下限 32：占位默认值一旦漏配就能签发出可用的管理员 token，
    # 且 8 位密钥可离线暴破。deploy/scripts/gen-secrets.sh 生成 64 位。
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 7200
    jwt_refresh_ttl_seconds: int = 604800

    # Permission cache
    permission_cache_ttl: int = 300

    # App Key Redis 映射
    app_key_redis_prefix: str = "fangyu:app_keys:"
    app_key_redis_ttl_seconds: int = 0  # 0 表示永久缓存，由 admin 侧显式清除

    # CORS
    # 默认空列表而非 ["*"]：通配来源配合 allow_credentials=True 会被浏览器直接
    # 拒绝，且等于放弃跨站防护。需要跨域时显式配置 ADMIN_CORS_ORIGINS（JSON 数组）。
    cors_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = True

    # Rate limiter
    login_rate_limit_per_minute: int = 10

    # 可观测性
    # 字段必须存在于此：main.py 用 getattr(settings, "otlp_endpoint", None) 读取，
    # 缺字段时永远拿到 None，导出器静默不启用。带前缀读取即 ADMIN_OTLP_ENDPOINT。
    otlp_endpoint: str | None = None
    """OTLP gRPC endpoint，如 http://jaeger:4317。为空则不导出 trace。"""
    trace_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    """采样率。生产建议 0.1~0.2，全采样在高 QPS 下开销显著。"""


_settings: AdminSettings | None = None


def get_settings() -> AdminSettings:
    global _settings
    if _settings is None:
        _settings = AdminSettings()
    return _settings

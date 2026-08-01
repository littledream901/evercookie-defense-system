"""Gateway 服务配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GATEWAY_",
        extra="ignore",
    )

    service_name: str = "gateway-api"
    version: str = "2.0.0"
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    log_level: str = "INFO"
    log_format: str = "json"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 100

    # ClickHouse (决策链路一般不直接查 CH，仅在需要时使用)
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_database: str = "fangyu"

    # Cache
    decision_cache_ttl: int = 60
    profile_cache_ttl: int = 3600

    # MMDB（MaxMind GeoLite2 双库：地理位置 + ASN）
    # 两个库缺任意一个都不影响启动，只会让对应维度的字段留空。
    mmdb_country_path: str = "/data/mmdb/GeoLite2-Country.mmdb"
    mmdb_asn_path: str = "/data/mmdb/GeoLite2-ASN.mmdb"

    # Risk thresholds
    challenge_threshold: float = Field(default=40.0, ge=0, le=100)
    block_threshold: float = Field(default=70.0, ge=0, le=100)

    # Stream
    event_stream_name: str = "fangyu:events:decision"
    event_stream_maxlen: int = 500_000

    # Security
    ip_blacklist: list[str] = Field(default_factory=list)
    country_blocklist: list[str] = Field(default_factory=list)
    block_tor: bool = True

    # App Key 校验
    app_key_required: bool = True
    app_key_header: str = "X-App-Key"
    app_key_redis_prefix: str = "fangyu:app_keys:"
    app_key_cache_ttl: int = 60
    app_key_cache_max_size: int = 4096

    # Clock：频控与行为时序
    clock_enabled: bool = True
    """关闭后流水线从 CACHE 开始，完全不产生 Clock 的 Redis 开销。"""

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True


_settings: GatewaySettings | None = None


def get_settings() -> GatewaySettings:
    global _settings
    if _settings is None:
        _settings = GatewaySettings()
    return _settings

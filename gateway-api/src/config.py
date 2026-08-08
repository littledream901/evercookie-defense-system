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

    # SDK 静态分发
    # client-sdk 的构建产物由 gateway-api.Dockerfile 的 sdk-builder 阶段
    # 编译并 COPY 到此目录，main.py 将其挂在 /sdk 路径上。
    # 目录不存在时跳过挂载而非启动失败：本地开发常不预构建 SDK，
    # 不该因此起不来网关。
    sdk_static_dir: str = "/app/static/sdk"

    # Risk thresholds
    # 累加截顶模型下的阈值，对齐原版 30/75 口径。
    # 早期加权平均模型用的 40/70 在累加语义下会过度触发，不可沿用。
    challenge_threshold: float = Field(default=30.0, ge=0, le=100)
    block_threshold: float = Field(default=75.0, ge=0, le=100)

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
    app_secret_redis_prefix: str = "fangyu:app_secrets:"
    """site_id → site_secret 反向索引前缀，供挑战凭据签发/校验按 site_id 取密钥。"""
    app_key_cache_ttl: int = 60
    app_key_cache_max_size: int = 4096

    # 请求签名（防伪造画像与重放）
    signature_required: bool = True
    """默认开启：关闭时任何人都能伪造 fingerprint / ip / behavior 上报，
    整条风控链路的输入不可信，等于没有防护。

    三个服务端适配器与浏览器 SDK 均已实现签名（待签串由 sign_vectors.json 锁定），
    所以默认开启不会拦掉自家流量。仅当存在未改造的第三方接入方时才临时置为
    false，且应视为待偿技术债——期间画像可被任意伪造。
    """
    signature_window: int = 300
    """timestamp 允许的双向偏差秒数，同时作为 nonce 的 Redis TTL。"""

    # Clock：频控与行为时序
    clock_enabled: bool = True
    """关闭后流水线从 CACHE 开始，完全不产生 Clock 的 Redis 开销。"""

    # 规则条件命中明细（decision_traces 冷表）
    decision_trace_enabled: bool = True
    """是否采集规则条件命中明细。

    关闭后 ``decision_traces`` 表不再有新数据，后台的「条件命中明细」排障视图
    会一直为空——只在明确不需要这项排障能力时关闭。
    """
    decision_trace_sample_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    """trusted 流量的明细采样率。非 trusted 裁决不受此值影响，一律全量留痕。

    默认 1%：正常流量是绝对多数，全量留痕会让这张冷表的写入量与主表持平，
    而它只用于排障对照。要看某个具体请求的明细时，被拦的那条一定在（非 trusted
    全量），trusted 的靠抽样覆盖。
    """

    # 白名单：误封的人工兜底通道
    whitelist_enabled: bool = True
    """关闭后流水线从 CLOCK 开始，省掉每请求一次 HMGET。

    默认开启：这是误封唯一的即时解除手段，关掉等于运维只能等封禁 TTL 自然
    过期。单次 HMGET 的成本远低于一次误封事故。
    """

    # CORS
    #
    # 这里保留 ["*"]：SDK 从各接入方站点发起跨域请求，来源无法预先枚举，
    # 收窄反而会拦掉正常流量。鉴权靠 API Key 请求头，不依赖 Cookie。
    #
    # 但 allow_credentials 必须默认 False —— 与 allow_origins=["*"] 同时开启时
    # 浏览器会直接拒绝整个响应，等于所有跨域请求失效。
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = False

    # 可观测性
    # 字段必须存在于此：main.py 用 getattr(settings, "otlp_endpoint", None) 读取，
    # 缺字段时永远拿到 None，导出器静默不启用。带前缀读取即 GATEWAY_OTLP_ENDPOINT。
    otlp_endpoint: str | None = None
    """OTLP gRPC endpoint，如 http://jaeger:4317。为空则不导出 trace。"""
    trace_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    """采样率。生产建议 0.1~0.2，全采样在高 QPS 下开销显著。"""


_settings: GatewaySettings | None = None


def get_settings() -> GatewaySettings:
    global _settings
    if _settings is None:
        _settings = GatewaySettings()
    return _settings

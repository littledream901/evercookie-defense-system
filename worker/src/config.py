"""Worker 配置。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="WORKER_",
        extra="ignore",
    )

    service_name: str = "worker"
    version: str = "2.0.0"
    log_level: str = "INFO"
    log_format: str = "json"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50

    # ClickHouse
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_database: str = "fangyu"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""

    # Stream
    stream_name: str = "fangyu:events:decision"
    consumer_group: str = "fangyu-worker"
    consumer_name: str = "worker-1"
    stream_batch_size: int = 200
    # 必须显著小于 Redis 客户端的 socket_timeout（默认 5s）。
    # 若两者相等，XREADGROUP BLOCK 阻塞满时长返回空结果的瞬间，
    # 客户端读超时同时到期，会抛 TimeoutError 并让消费循环崩溃。
    stream_block_ms: int = 2000
    stream_claim_min_idle_ms: int = 60_000

    # Batch writer
    batch_size: int = 500
    batch_flush_interval_seconds: float = 5.0
    batch_target_table: str = "fangyu.decision_events"

    # Retry / DLQ
    max_retries: int = 3
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 30.0
    dead_letter_stream: str = "fangyu:events:decision:dlq"
    dead_letter_maxlen: int = 100_000

    # Health
    health_port: int = 9091
    metrics_port: int = 9092

    # Concurrency
    concurrency: int = Field(default=2, ge=1, le=32)

    # Reputation writer（周期回流）
    reputation_enabled: bool = True
    reputation_sync_interval_seconds: float = 3600.0
    """每隔多少秒触发一次声誉回流。"""
    reputation_lookback_days: int = 7
    """向前追溯天数，覆盖足够历史让分数更稳定。"""
    reputation_min_samples: int = 5
    """最少样本数门槛，样本不足的记录跳过写入。"""
    reputation_ip_ttl: int = 86_400
    """IP 画像在 Redis 中的过期时间（秒）。"""
    reputation_device_ttl: int = 86_400
    """设备画像过期时间（秒）。"""


_settings: WorkerSettings | None = None


def get_settings() -> WorkerSettings:
    global _settings
    if _settings is None:
        _settings = WorkerSettings()
    return _settings

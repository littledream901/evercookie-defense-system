"""Redis 配置对象."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedisConfig:
    """Redis 连接配置."""

    url: str = "redis://localhost:6379/0"
    max_connections: int = 100
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 2.0
    retry_on_timeout: bool = True
    decode_responses: bool = True
    health_check_interval: int = 30

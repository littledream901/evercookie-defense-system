"""ClickHouse 连接配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClickHouseConfig:
    """ClickHouse 连接配置。

    使用 aiochclient 走 HTTP 协议以获得更好的异步支持；
    对于批量写入或 native 协议的重负载，可另外提供 clickhouse-driver 客户端。
    """

    url: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_URL", "http://localhost:8123"))
    database: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_DATABASE", "fangyu"))
    user: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_USER", "default"))
    password: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_PASSWORD", ""))
    connect_timeout: float = 5.0
    request_timeout: float = 30.0
    max_pool_size: int = 20
    compress_response: bool = True

    def to_client_kwargs(self) -> dict[str, Any]:
        """转换为 aiochclient 可接受的关键字参数。"""
        return {
            "url": self.url,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "compress_response": self.compress_response,
        }

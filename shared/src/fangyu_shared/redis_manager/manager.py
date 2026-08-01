"""全局 Redis 连接池管理器（单例）."""

from __future__ import annotations

import logging
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from .config import RedisConfig

logger = logging.getLogger(__name__)


class RedisManager:
    """全局 Redis 连接池管理器（进程级单例）."""

    _pool: ConnectionPool | None = None
    _config: RedisConfig | None = None

    @classmethod
    async def init(cls, config: RedisConfig | None = None) -> None:
        """初始化连接池.

        重复调用会自动关闭旧连接池并使用新配置。
        """
        if cls._pool is not None:
            await cls.close()

        cfg = config or RedisConfig()
        retry = Retry(ExponentialBackoff(cap=2, base=0.1), retries=3)

        cls._pool = ConnectionPool.from_url(
            cfg.url,
            max_connections=cfg.max_connections,
            socket_timeout=cfg.socket_timeout,
            socket_connect_timeout=cfg.socket_connect_timeout,
            retry_on_timeout=cfg.retry_on_timeout,
            decode_responses=cfg.decode_responses,
            health_check_interval=cfg.health_check_interval,
            retry=retry,
        )
        cls._config = cfg
        logger.info(
            "redis_pool_initialized",
            extra={"max_connections": cfg.max_connections, "url": cfg.url},
        )

    @classmethod
    def get_client(cls) -> Redis:
        """获取 Redis 客户端实例."""
        if cls._pool is None:
            raise RuntimeError("RedisManager 未初始化，请先调用 RedisManager.init(config)")
        return Redis(connection_pool=cls._pool)

    @classmethod
    def is_initialized(cls) -> bool:
        """是否已初始化连接池."""
        return cls._pool is not None

    @classmethod
    async def close(cls) -> None:
        """关闭连接池."""
        if cls._pool is not None:
            await cls._pool.disconnect(inuse_connections=True)
            cls._pool = None
            cls._config = None
            logger.info("redis_pool_closed")

    @classmethod
    async def ping(cls) -> bool:
        """探测 Redis 是否可用."""
        try:
            client = cls.get_client()
            pong = await client.ping()
            return bool(pong)
        except Exception as e:  # pragma: no cover
            logger.warning("redis_ping_failed", extra={"error": str(e)})
            return False


def get_redis() -> Redis[Any]:
    """便捷函数：获取当前 Redis 客户端."""
    return RedisManager.get_client()

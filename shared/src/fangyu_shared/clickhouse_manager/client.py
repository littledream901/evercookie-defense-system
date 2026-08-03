"""ClickHouse 异步客户端与管理器。

基于 aiochclient（HTTP 协议）实现，避免同步驱动阻塞事件循环。
提供统一的单例 ClickHouseManager 与依赖注入函数 get_clickhouse。
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from aiochclient import ChClient

from fangyu_shared.clickhouse_manager.config import ClickHouseConfig


class ClickHouseClient:
    """对 aiochclient 的轻量封装，负责底层查询与写入。"""

    def __init__(self, chclient: ChClient, config: ClickHouseConfig) -> None:
        self._client = chclient
        self._config = config

    @property
    def database(self) -> str:
        """当前连接的库名。供需要拼接全限定表名的查询层读取。"""
        return self._config.database

    async def fetch(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """执行 SELECT 并返回 list[dict]。"""
        rows = await self._client.fetch(sql, params=params or {})
        return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        row = await self._client.fetchrow(sql, params=params or {})
        return dict(row) if row is not None else None

    async def fetch_val(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        return await self._client.fetchval(sql, params=params or {})

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        await self._client.execute(sql, params=params or {})

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        """批量插入。

        aiochclient 的批量写入协议：SQL 以 `VALUES` 结尾（不带占位符），
        行数据以位置参数（每行一个 tuple）传入，由客户端负责类型序列化。
        写成 `VALUES (%s, %s, ...)` 会被 ClickHouse 当字面量解析，
        报 `Cannot parse expression of type String here: %s` 并导致数据全量进死信队列。
        """
        if not rows:
            return
        columns = list(rows[0].keys())
        col_expr = ", ".join(columns)
        values = [tuple(row.get(c) for c in columns) for row in rows]
        sql = f"INSERT INTO {table} ({col_expr}) VALUES"
        await self._client.execute(sql, *values)

    async def ping(self) -> bool:
        try:
            return await self._client.is_alive()
        except Exception:
            return False


class ClickHouseManager:
    """全局 ClickHouse 客户端单例。"""

    _client: ClickHouseClient | None = None
    _session: aiohttp.ClientSession | None = None
    _config: ClickHouseConfig | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def init(cls, config: ClickHouseConfig | None = None) -> None:
        async with cls._lock:
            if cls._client is not None:
                await cls._close_locked()
            cfg = config or ClickHouseConfig()
            timeout = aiohttp.ClientTimeout(
                total=cfg.request_timeout,
                connect=cfg.connect_timeout,
            )
            connector = aiohttp.TCPConnector(limit=cfg.max_pool_size)
            cls._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            chclient = ChClient(cls._session, **cfg.to_client_kwargs())
            cls._client = ClickHouseClient(chclient, cfg)
            cls._config = cfg

    @classmethod
    def get_client(cls) -> ClickHouseClient:
        if cls._client is None:
            raise RuntimeError("ClickHouseManager 未初始化，请先调用 ClickHouseManager.init(config)")
        return cls._client

    @classmethod
    async def close(cls) -> None:
        async with cls._lock:
            await cls._close_locked()

    @classmethod
    async def _close_locked(cls) -> None:
        if cls._session is not None:
            await cls._session.close()
        cls._client = None
        cls._session = None
        cls._config = None

    @classmethod
    async def ping(cls) -> bool:
        if cls._client is None:
            return False
        return await cls._client.ping()

    @classmethod
    def is_initialized(cls) -> bool:
        return cls._client is not None


def get_clickhouse() -> ClickHouseClient:
    """FastAPI 依赖注入辅助函数。"""
    return ClickHouseManager.get_client()

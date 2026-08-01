"""SQLAlchemy 2.0 异步会话管理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型基类。"""


class Database:
    _engine: AsyncEngine | None = None
    _sessionmaker: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def init(
        cls,
        url: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_recycle: int = 3600,
        echo: bool = False,
    ) -> None:
        cls._engine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            echo=echo,
        )
        cls._sessionmaker = async_sessionmaker(
            bind=cls._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @classmethod
    async def close(cls) -> None:
        if cls._engine is not None:
            await cls._engine.dispose()
        cls._engine = None
        cls._sessionmaker = None

    @classmethod
    def engine(cls) -> AsyncEngine:
        if cls._engine is None:
            raise RuntimeError("Database 未初始化")
        return cls._engine

    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncIterator[AsyncSession]:
        if cls._sessionmaker is None:
            raise RuntimeError("Database 未初始化")
        async with cls._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

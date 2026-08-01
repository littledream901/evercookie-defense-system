"""Alembic 环境配置。

- 通过 admin-api 的 AdminSettings 读取数据库 URL，允许被环境变量覆盖。
- metadata 直接使用 SQLAlchemy Base.metadata，保证与业务模型一致。
- 同步/异步双通道：默认走 async engine；如果 URL 使用同步驱动，退回同步流程。
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

_HERE = Path(__file__).resolve().parent
_ADMIN_ROOT = _HERE.parent
_SRC_DIR = _ADMIN_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from src.config import get_settings  # noqa: E402
from src.infrastructure.database import Base  # noqa: E402
from src.infrastructure.repositories import models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_env_url = os.getenv("ADMIN_DATABASE_URL") or os.getenv("ALEMBIC_DATABASE_URL")
_db_url = _env_url or get_settings().database_url
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def _is_async_url(url: str) -> bool:
    return "+aiomysql" in url or "+asyncmy" in url or "+asyncpg" in url


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def _run_sync_migrations() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _do_run_migrations(connection)
    connectable.dispose()


def run_migrations_online() -> None:
    if _is_async_url(config.get_main_option("sqlalchemy.url") or ""):
        asyncio.run(_run_async_migrations())
    else:
        _run_sync_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

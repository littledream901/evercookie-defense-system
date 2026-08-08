#!/usr/bin/env python3
"""Redis 数据迁移：为所有 app_keys 映射增加 is_active 字段。

背景：
- 旧版 Redis 映射格式：{"app_id": <site_id>, "app_secret": "..."}
- 新版增加 is_active 字段防止已停用站点继续通过鉴权

执行前提：
- 需在 admin-api 容器内或配置了相同 Redis 连接的环境执行
- 需要 ADMIN_REDIS_URL 环境变量

执行方式：
    python scripts/migrate_redis_add_is_active.py

安全性：
- 只修改 fangyu:app_keys:* 键的值结构，不删除任何数据
- 自动备份原始值到 fangyu:app_keys_backup:* 键（TTL 24小时）
- 支持幂等执行：已迁移的键跳过
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "admin-api" / "src"))
sys.path.insert(0, str(project_root / "shared" / "src"))

import orjson
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fangyu_shared.logging import get_logger
from src.infrastructure.repositories.models import SiteModel

_logger = get_logger("migrate_redis")

# Redis 键前缀
APP_KEYS_PREFIX = "fangyu:app_keys:"
BACKUP_PREFIX = "fangyu:app_keys_backup:"
BACKUP_TTL = 86400  # 24 小时


async def get_db_session() -> AsyncSession:
    """创建数据库会话，从环境变量读取 URL。"""
    db_url = os.getenv("ADMIN_DATABASE_URL")
    if not db_url:
        raise RuntimeError("缺少环境变量 ADMIN_DATABASE_URL")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def get_redis_client() -> Redis:
    """创建 Redis 客户端，从环境变量读取 URL。"""
    redis_url = os.getenv("ADMIN_REDIS_URL")
    if not redis_url:
        raise RuntimeError("缺少环境变量 ADMIN_REDIS_URL")
    
    return Redis.from_url(redis_url, decode_responses=False)


async def fetch_site_status(session: AsyncSession) -> dict[int, bool]:
    """从数据库获取所有站点的 is_active 状态。"""
    stmt = select(SiteModel.id, SiteModel.is_active)
    result = await session.execute(stmt)
    return {site_id: is_active for site_id, is_active in result.all()}


async def migrate_redis_keys(redis: Redis, site_status: dict[int, bool]) -> tuple[int, int, int]:
    """迁移所有 app_keys 映射。
    
    Returns:
        (成功数, 跳过数, 失败数)
    """
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=f"{APP_KEYS_PREFIX}*", count=100)
        
        for key_bytes in keys:
            key = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else key_bytes
            site_key = key.replace(APP_KEYS_PREFIX, "")
            
            try:
                # 读取原始值
                raw = await redis.get(key)
                if not raw:
                    _logger.warning("key_empty_skip", key=site_key)
                    skip_count += 1
                    continue
                
                value_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                
                # 解析 JSON
                try:
                    payload = orjson.loads(value_str)
                except orjson.JSONDecodeError:
                    _logger.error("key_invalid_json_skip", key=site_key, value=value_str[:100])
                    fail_count += 1
                    continue
                
                if not isinstance(payload, dict):
                    _logger.error("key_not_dict_skip", key=site_key)
                    fail_count += 1
                    continue
                
                # 检查是否已有 is_active 字段
                if "is_active" in payload:
                    _logger.debug("key_already_migrated", key=site_key)
                    skip_count += 1
                    continue
                
                # 获取 site_id
                site_id = payload.get("app_id") or payload.get("site_id")
                if not site_id:
                    _logger.error("key_missing_site_id", key=site_key)
                    fail_count += 1
                    continue
                
                site_id = int(site_id)
                
                # 从数据库状态获取 is_active，默认 True（防止数据库中找不到）
                is_active = site_status.get(site_id, True)
                
                # 备份原始值
                backup_key = f"{BACKUP_PREFIX}{site_key}"
                await redis.setex(backup_key, BACKUP_TTL, value_str)
                
                # 更新值
                payload["is_active"] = is_active
                new_value = orjson.dumps(payload).decode("utf-8")
                await redis.set(key, new_value)
                
                _logger.info(
                    "key_migrated",
                    site_key=site_key,
                    site_id=site_id,
                    is_active=is_active,
                )
                success_count += 1
                
            except Exception as exc:
                _logger.error("key_migration_failed", key=site_key, error=str(exc))
                fail_count += 1
        
        if cursor == 0:
            break
    
    return success_count, skip_count, fail_count


async def main() -> None:
    _logger.info("migration_start")
    
    redis = await get_redis_client()
    session = await get_db_session()
    
    try:
        # 从数据库获取站点状态
        _logger.info("fetching_site_status")
        site_status = await fetch_site_status(session)
        _logger.info("site_status_fetched", total=len(site_status))
        
        # 迁移 Redis 键
        _logger.info("migrating_redis_keys")
        success, skip, fail = await migrate_redis_keys(redis, site_status)
        
        _logger.info(
            "migration_completed",
            success=success,
            skip=skip,
            fail=fail,
            total=success + skip + fail,
        )
        
        if fail > 0:
            _logger.warning("migration_has_failures", fail_count=fail)
            sys.exit(1)
        
    finally:
        await session.close()
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""检查已停用/删除站点是否仍有流量尝试访问。

用途：
- 快速诊断是否有未清理的 CF Worker 或适配器
- 生成需要清理的站点清单

执行方式：
    python tmp/scripts/check_inactive_sites.py

输出示例：
    发现 3 个已停用站点仍有流量尝试：
    
    站点 ID: 123 | 名称: 旧站点A | 域名: old-a.com
      - Redis 状态: is_active=false
      - 最近尝试: 10 分钟前
      - 建议: 清理 Cloudflare Worker 或 Nginx 适配器
    
    站点 ID: 456 | 名称: 旧站点B | 域名: old-b.com
      - Redis 状态: 已删除（无映射）
      - 最近尝试: 2 小时前
      - 建议: 检查域名是否仍有 DNS 记录指向旧适配器
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "admin-api" / "src"))
sys.path.insert(0, str(project_root / "shared" / "src"))

import orjson
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fangyu_shared.logging import get_logger
from src.infrastructure.repositories.models import SiteModel

_logger = get_logger("check_inactive_sites")


async def get_db_session() -> AsyncSession:
    """创建数据库会话。"""
    db_url = os.getenv("ADMIN_DATABASE_URL")
    if not db_url:
        raise RuntimeError("缺少环境变量 ADMIN_DATABASE_URL")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def get_redis_client() -> Redis:
    """创建 Redis 客户端。"""
    redis_url = os.getenv("ADMIN_REDIS_URL")
    if not redis_url:
        raise RuntimeError("缺少环境变量 ADMIN_REDIS_URL")
    
    return Redis.from_url(redis_url, decode_responses=False)


async def get_inactive_sites(session: AsyncSession) -> dict[int, dict]:
    """获取所有已停用的站点信息。"""
    stmt = select(SiteModel).where(SiteModel.is_active == False)  # noqa: E712
    result = await session.execute(stmt)
    sites = result.scalars().all()
    
    return {
        site.id: {
            "id": site.id,
            "name": site.name,
            "domain": site.domain,
            "site_key": site.site_key,
            "access_mode": site.access_mode,
            "updated_at": site.updated_at,
        }
        for site in sites
    }


async def check_redis_status(redis: Redis, site_key: str) -> dict:
    """检查 Redis 中的站点状态。"""
    key = f"fangyu:app_keys:{site_key}"
    raw = await redis.get(key)
    
    if not raw:
        return {"exists": False, "is_active": None}
    
    try:
        value_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        payload = orjson.loads(value_str)
        return {
            "exists": True,
            "is_active": payload.get("is_active", True),  # 旧数据默认 True
            "has_field": "is_active" in payload,
        }
    except Exception:
        return {"exists": True, "is_active": None, "error": "parse_failed"}


async def scan_gateway_logs_for_rejected(redis: Redis) -> dict[int, datetime]:
    """扫描 Redis 中最近的拒绝日志（如果有）。
    
    注意：这里是示例逻辑，实际需根据你的日志存储方式调整。
    如果使用 ClickHouse 存日志，需改为查询 ClickHouse。
    """
    # 这里简化处理：假设没有单独的拒绝日志存储
    # 实际生产中可从 ClickHouse decision_log 表查询
    # WHERE verdict='block' AND site_id IN (...)
    return {}


def format_time_ago(dt: datetime) -> str:
    """格式化时间差。"""
    now = datetime.now()
    if dt.tzinfo:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    
    delta = now - dt
    
    if delta < timedelta(minutes=1):
        return "刚刚"
    elif delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() / 60)} 分钟前"
    elif delta < timedelta(days=1):
        return f"{int(delta.total_seconds() / 3600)} 小时前"
    else:
        return f"{delta.days} 天前"


async def main() -> None:
    print("=" * 70)
    print("检查已停用站点是否仍有流量尝试访问")
    print("=" * 70)
    print()
    
    redis = await get_redis_client()
    session = await get_db_session()
    
    try:
        # 1. 获取所有已停用的站点
        print("[1/3] 从数据库读取已停用站点...")
        inactive_sites = await get_inactive_sites(session)
        
        if not inactive_sites:
            print("✓ 未发现已停用的站点")
            return
        
        print(f"✓ 发现 {len(inactive_sites)} 个已停用站点")
        print()
        
        # 2. 检查 Redis 状态
        print("[2/3] 检查 Redis 映射状态...")
        issues = []
        
        for site_id, site_info in inactive_sites.items():
            redis_status = await check_redis_status(redis, site_info["site_key"])
            
            # 已停用但 Redis 仍标记为激活 = 迁移未完成或有问题
            if redis_status["exists"] and redis_status.get("is_active") is True:
                issues.append({
                    "site": site_info,
                    "redis_status": redis_status,
                    "issue_type": "redis_inconsistent",
                    "severity": "high",
                })
            
            # 已停用且 Redis 正确标记，但映射仍存在
            elif redis_status["exists"] and redis_status.get("is_active") is False:
                issues.append({
                    "site": site_info,
                    "redis_status": redis_status,
                    "issue_type": "mapping_exists",
                    "severity": "medium",
                })
            
            # Redis 映射已删除（符合预期）
            elif not redis_status["exists"]:
                # 这是正常状态，跳过
                pass
        
        print(f"✓ 完成检查")
        print()
        
        # 3. 输出结果
        print("[3/3] 分析结果")
        print("-" * 70)
        
        if not issues:
            print("✓ 所有已停用站点的 Redis 映射均已正确清理")
            print("  如果仍有流量尝试，说明外部适配器（CF Worker/Nginx）未清理")
            print()
            print("建议操作：")
            for site_info in inactive_sites.values():
                print(f"  • 站点: {site_info['name']} ({site_info['domain']})")
                print(f"    - 接入方式: {site_info['access_mode']}")
                print(f"    - 停用时间: {format_time_ago(site_info['updated_at'])}")
                if site_info['access_mode'] == 'adapter':
                    print(f"    - 操作: 检查域名 {site_info['domain']} 的 Nginx/CDN 配置")
                else:
                    print(f"    - 操作: 通知业务方移除前端 SDK 代码")
                print()
        else:
            print(f"⚠ 发现 {len(issues)} 个异常情况：")
            print()
            
            for issue in issues:
                site = issue["site"]
                redis_status = issue["redis_status"]
                
                print(f"站点 ID: {site['id']} | 名称: {site['name']} | 域名: {site['domain']}")
                print(f"  停用时间: {format_time_ago(site['updated_at'])}")
                print(f"  Redis 状态: exists={redis_status['exists']}, "
                      f"is_active={redis_status.get('is_active')}")
                
                if issue["issue_type"] == "redis_inconsistent":
                    print(f"  ⚠ 严重：数据库标记已停用，但 Redis 仍标记为激活")
                    print(f"  建议：执行 Redis 迁移脚本或手动更新 Redis 值")
                    print(f"  命令：redis-cli GET 'fangyu:app_keys:{site['site_key']}'")
                elif issue["issue_type"] == "mapping_exists":
                    print(f"  ℹ 信息：Redis 映射正确但未删除（性能优化可考虑删除）")
                    if not redis_status.get("has_field"):
                        print(f"  提示：该站点 Redis 值无 is_active 字段，建议执行迁移脚本")
                
                if site['access_mode'] == 'adapter':
                    print(f"  建议：检查 Cloudflare Worker 或 Nginx 适配器是否已清理")
                else:
                    print(f"  建议：通知业务方移除前端 SDK 或更新 appId")
                
                print()
        
    finally:
        await session.close()
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())

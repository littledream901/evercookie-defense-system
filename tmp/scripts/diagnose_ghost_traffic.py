#!/usr/bin/env python3
"""快速诊断：分析访问日志中的异常站点流量。

用途：
- 快速找出哪些已删除/停用站点仍在产生流量
- 生成需要清理的 CF Worker / 适配器清单
- 提供具体的清理步骤

执行方式：
    python tmp/scripts/diagnose_ghost_traffic.py

需要环境变量：
    ADMIN_DATABASE_URL - 数据库连接
    CLICKHOUSE_URL - ClickHouse 连接（可选，用于分析日志）
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "admin-api" / "src"))
sys.path.insert(0, str(project_root / "shared" / "src"))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fangyu_shared.logging import get_logger
from src.infrastructure.repositories.models import SiteModel

_logger = get_logger("diagnose_ghost_traffic")


async def get_db_session() -> AsyncSession:
    db_url = os.getenv("ADMIN_DATABASE_URL")
    if not db_url:
        raise RuntimeError("缺少环境变量 ADMIN_DATABASE_URL")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def get_all_sites(session: AsyncSession) -> dict[int, dict]:
    """获取所有站点信息。"""
    stmt = select(SiteModel)
    result = await session.execute(stmt)
    sites = result.scalars().all()
    
    return {
        site.id: {
            "id": site.id,
            "name": site.name,
            "domain": site.domain,
            "site_key": site.site_key,
            "is_active": site.is_active,
            "access_mode": site.access_mode,
            "updated_at": site.updated_at,
        }
        for site in sites
    }


async def analyze_recent_traffic(session: AsyncSession) -> dict[int, int]:
    """从 decision_log 表分析最近的流量（如果表存在）。
    
    Returns:
        {site_id: request_count}
    """
    try:
        # 检查表是否存在
        stmt = text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND table_name = 'decision_log'
        """)
        result = await session.execute(stmt)
        if not result.scalar():
            _logger.warning("decision_log 表不存在，跳过日志分析")
            return {}
        
        # 统计最近 1 小时的流量
        stmt = text("""
            SELECT site_id, COUNT(*) as cnt
            FROM decision_log
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            GROUP BY site_id
            ORDER BY cnt DESC
        """)
        result = await session.execute(stmt)
        return {row.site_id: row.cnt for row in result}
    
    except Exception as exc:
        _logger.warning(f"分析流量失败: {exc}")
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
    print("=" * 80)
    print("快速诊断：已删除/停用站点仍产生流量")
    print("=" * 80)
    print()
    
    session = await get_db_session()
    
    try:
        # 1. 获取所有站点
        print("[1/2] 读取站点信息...")
        all_sites = await get_all_sites(session)
        active_sites = {sid: info for sid, info in all_sites.items() if info["is_active"]}
        inactive_sites = {sid: info for sid, info in all_sites.items() if not info["is_active"]}
        
        print(f"  - 激活站点: {len(active_sites)} 个")
        print(f"  - 停用站点: {len(inactive_sites)} 个")
        print()
        
        # 2. 分析最近流量
        print("[2/2] 分析最近 1 小时流量...")
        traffic = await analyze_recent_traffic(session)
        
        if not traffic:
            print("  ⚠ 无法从数据库分析流量（decision_log 表不存在或无数据）")
            print("  建议：直接检查所有已停用站点")
            print()
        else:
            print(f"  - 总请求数: {sum(traffic.values())} 次")
            print()
        
        # 3. 找出异常情况
        print("=" * 80)
        print("诊断结果")
        print("=" * 80)
        print()
        
        ghost_traffic = []
        
        for site_id, count in traffic.items():
            if site_id in inactive_sites:
                ghost_traffic.append((site_id, inactive_sites[site_id], count))
            elif site_id not in all_sites:
                ghost_traffic.append((site_id, {"name": "已删除", "domain": "未知", "site_key": "未知"}, count))
        
        if not ghost_traffic and not inactive_sites:
            print("✅ 未发现异常流量")
            print()
            return
        
        if ghost_traffic:
            print(f"🔴 发现 {len(ghost_traffic)} 个已停用/删除站点仍有流量：")
            print()
            
            for site_id, info, count in sorted(ghost_traffic, key=lambda x: x[2], reverse=True):
                print(f"站点 ID: {site_id}")
                print(f"  名称: {info.get('name', '未知')}")
                print(f"  域名: {info.get('domain', '未知')}")
                print(f"  最近 1 小时请求数: {count} 次")
                print(f"  接入方式: {info.get('access_mode', '未知')}")
                
                if info.get("access_mode") == "adapter":
                    print(f"  ⚠️  问题: Cloudflare Worker 或 Nginx 适配器未清理")
                    print(f"  解决步骤:")
                    print(f"    1. 登录 Cloudflare Dashboard")
                    print(f"    2. 找到域名 {info.get('domain', '未知')} 的 Workers")
                    print(f"    3. 停用或删除对应的 Worker")
                else:
                    print(f"  ⚠️  问题: 前端 SDK 代码未移除")
                    print(f"  解决步骤:")
                    print(f"    1. 通知业务方")
                    print(f"    2. 移除前端页面的 fangyu-sdk.js 引用")
                    print(f"    3. 或更新 SDK 的 appId 配置")
                
                print()
        
        if inactive_sites and not ghost_traffic:
            print(f"ℹ️  发现 {len(inactive_sites)} 个已停用站点，但最近 1 小时无流量")
            print()
            print("建议检查这些站点的外部适配器是否已清理：")
            print()
            
            for site_id, info in list(inactive_sites.items())[:5]:
                print(f"  • {info['name']} ({info['domain']})")
                print(f"    停用时间: {format_time_ago(info['updated_at'])}")
                print(f"    接入方式: {info['access_mode']}")
            
            if len(inactive_sites) > 5:
                print(f"  ... 还有 {len(inactive_sites) - 5} 个站点")
            print()
        
        # 4. 生成清理检查清单
        print("=" * 80)
        print("清理检查清单")
        print("=" * 80)
        print()
        
        if not inactive_sites:
            print("✅ 无需清理")
            return
        
        adapter_sites = [s for s in inactive_sites.values() if s["access_mode"] == "adapter"]
        sdk_sites = [s for s in inactive_sites.values() if s["access_mode"] == "sdk"]
        
        if adapter_sites:
            print("📋 需要清理的 Cloudflare Worker / Nginx 适配器：")
            print()
            for site in adapter_sites:
                print(f"  [ ] {site['domain']}")
                print(f"      站点名: {site['name']}")
                print(f"      停用时间: {format_time_ago(site['updated_at'])}")
            print()
        
        if sdk_sites:
            print("📋 需要通知业务方移除 SDK 的站点：")
            print()
            for site in sdk_sites:
                print(f"  [ ] {site['domain']}")
                print(f"      站点名: {site['name']}")
                print(f"      停用时间: {format_time_ago(site['updated_at'])}")
            print()
    
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())

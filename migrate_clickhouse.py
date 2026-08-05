#!/usr/bin/env python3
"""
ClickHouse 迁移脚本：应用 v4 (host) 和 v5 (is_vpn/is_proxy)
用法：python3 migrate_clickhouse.py
"""
import asyncio
import os
import sys
from pathlib import Path

try:
    from aiochclient import ChClient
    from aiohttp import ClientSession
except ImportError:
    print("缺少依赖，正在安装...")
    os.system(f"{sys.executable} -m pip install aiochclient aiohttp -q")
    from aiochclient import ChClient
    from aiohttp import ClientSession


async def main():
    # 从环境变量读取 ClickHouse 配置（与 admin-api 保持一致）
    ch_url = os.getenv("ADMIN_CLICKHOUSE_URL", "http://localhost:8123")
    ch_db = os.getenv("ADMIN_CLICKHOUSE_DATABASE", "fangyu")
    ch_user = os.getenv("ADMIN_CLICKHOUSE_USER", "default")
    ch_pass = os.getenv("ADMIN_CLICKHOUSE_PASSWORD", "")

    print(f"连接到 ClickHouse: {ch_url} (database={ch_db})")

    migrations = [
        ("v4: host 列", 
         "ALTER TABLE {db}.decision_events "
         "ADD COLUMN IF NOT EXISTS host String DEFAULT '' AFTER user_agent"),
        
        ("v5: is_vpn 列",
         "ALTER TABLE {db}.decision_events "
         "ADD COLUMN IF NOT EXISTS is_vpn UInt8 DEFAULT 0 AFTER connection_type"),
        
        ("v5: is_proxy 列",
         "ALTER TABLE {db}.decision_events "
         "ADD COLUMN IF NOT EXISTS is_proxy UInt8 DEFAULT 0 AFTER is_vpn"),
    ]

    async with ClientSession() as session:
        client = ChClient(session, url=ch_url, database=ch_db, 
                         user=ch_user, password=ch_pass)

        for label, sql_template in migrations:
            sql = sql_template.format(db=ch_db)
            try:
                await client.execute(sql)
                print(f"✓ {label}")
            except Exception as e:
                print(f"✗ {label} 失败: {e}")
                return 1

        # 验证
        cols = await client.fetch(
            f"SELECT name FROM system.columns "
            f"WHERE database = '{ch_db}' AND table = 'decision_events'"
        )
        actual = {c['name'] for c in cols}
        
        print("\n迁移后验证：")
        for col in ('host', 'is_vpn', 'is_proxy'):
            status = "✓ 存在" if col in actual else "✗ 缺失"
            print(f"  {col:<12} {status}")

        # 测试查询
        try:
            await client.fetch(
                f"SELECT host, is_vpn, is_proxy FROM {ch_db}.decision_events LIMIT 1"
            )
            print("\n✓ 完整性检查通过，admin-api 可以正常查询")
            return 0
        except Exception as e:
            print(f"\n✗ 查询测试失败: {e}")
            return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

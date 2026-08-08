#!/usr/bin/env python3
"""检查ClickHouse表结构"""
import sys
from pathlib import Path
import httpx

CLICKHOUSE_URL = "http://192.168.0.121:8123"

# 查询表结构
sql = """
SELECT name, type, default_expression
FROM system.columns
WHERE database = 'fangyu' 
  AND table = 'decision_events'
ORDER BY position
"""

try:
    response = httpx.post(
        CLICKHOUSE_URL,
        content=sql,
        timeout=10.0
    )
    
    if response.status_code == 200:
        print("✅ ClickHouse表结构查询成功\n")
        print("字段列表:")
        print("=" * 80)
        lines = response.text.strip().split("\n")
        for i, line in enumerate(lines, 1):
            print(f"{i:3d}. {line}")
        
        # 检查关键字段
        print("\n" + "=" * 80)
        print("关键字段检查:")
        required_fields = ['asn_org', 'crawler_name', 'crawler_category', 'crawler_vendor']
        for field in required_fields:
            if field in response.text:
                print(f"  ✅ {field}")
            else:
                print(f"  ❌ {field} - 缺失!")
    else:
        print(f"❌ 查询失败: {response.status_code}")
        print(response.text)
        sys.exit(1)
        
except Exception as e:
    print(f"❌ 执行出错: {e}")
    sys.exit(1)

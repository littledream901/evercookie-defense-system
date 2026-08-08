#!/usr/bin/env python3
"""检查is_bot字段是否存在"""
import httpx

CLICKHOUSE_URL = "http://192.168.0.121:8123"

sql = """
SELECT name, type, default_expression, position
FROM system.columns
WHERE database = 'fangyu' 
  AND table = 'decision_events'
  AND position BETWEEN 30 AND 36
ORDER BY position
"""

response = httpx.post(CLICKHOUSE_URL, content=sql, timeout=10.0)
print("位置30-36的字段:")
print(response.text)

# 检查is_bot
sql2 = "SELECT name FROM system.columns WHERE database = 'fangyu' AND table = 'decision_events' AND name = 'is_bot'"
response2 = httpx.post(CLICKHOUSE_URL, content=sql2, timeout=10.0)
if response2.text.strip():
    print(f"\n✅ is_bot字段存在")
else:
    print(f"\n❌ is_bot字段不存在，需要添加")

#!/usr/bin/env python3
"""执行ClickHouse数据库迁移脚本"""
import sys
from pathlib import Path
import httpx

# 读取环境变量
CLICKHOUSE_URL = "http://192.168.0.121:8123"

# 读取迁移SQL
import sys
if len(sys.argv) > 1:
    migration_name = sys.argv[1]
else:
    migration_name = "20260807_add_crawler_name.sql"

migration_file = Path(__file__).parent.parent / "infrastructure" / "clickhouse" / "migrations" / migration_name
if not migration_file.exists():
    print(f"❌ 迁移文件不存在: {migration_file}")
    sys.exit(1)

sql_content = migration_file.read_text(encoding="utf-8")

# 提取所有ALTER TABLE语句（多行合并）
alter_statements = []
lines = []
in_alter = False

for line in sql_content.split("\n"):
    stripped = line.strip()
    
    # 跳过注释和验证查询
    if stripped.startswith("--") or stripped.startswith("SELECT"):
        continue
    
    if stripped.startswith("ALTER TABLE"):
        in_alter = True
        lines = [stripped]
    elif in_alter and stripped:
        lines.append(stripped)
        if stripped.endswith(";"):
            alter_statements.append(" ".join(lines).strip())
            in_alter = False
            lines = []

if not alter_statements:
    print("❌ 未找到ALTER TABLE语句")
    sys.exit(1)

print(f"找到 {len(alter_statements)} 个迁移语句\n")

success_count = 0
for i, alter_sql in enumerate(alter_statements, 1):
    print(f"执行迁移SQL ({i}/{len(alter_statements)}):")
    print(f"  {alter_sql[:80]}...")
    print()

    try:
        # 执行ALTER TABLE
        response = httpx.post(
            CLICKHOUSE_URL,
            content=alter_sql,
            timeout=30.0
        )
        
        if response.status_code == 200:
            print(f"✅ 迁移 {i} 执行成功")
            success_count += 1
        else:
            print(f"❌ 迁移 {i} 失败: {response.status_code}")
            print(response.text)
            sys.exit(1)
    except Exception as e:
        print(f"❌ 迁移 {i} 执行出错: {e}")
        sys.exit(1)
    
    print()

print(f"✅ 全部完成: {success_count}/{len(alter_statements)} 个迁移成功执行\n")

#!/usr/bin/env python3
"""清理所有历史遗留注释"""
import re
from pathlib import Path

# 需要清理的模式
PATTERNS = [
    (r'历史遗留.*?(?=\n)', ''),
    (r'历史列名.*?(?=\n)', ''),
    (r'，这是历史遗留的命名问题。', ''),
    (r'。注意：历史遗留命名，实际是站点ID而非应用ID', ''),
    (r'对应 ClickHouse 的 app_id 列（历史列名，实际存储站点ID）', ''),
    (r'注意：Redis 中的 app_id 字段实际存储的是站点主键\(Site\.id\)，这是历史遗留命名。', 
     'Redis 键中的 site_id 字段对应站点主键（Site.id）。'),
    (r'ClickHouse 的 app_id 列实际存储的是 site_id（历史遗留，未重命名）', ''),
    (r'列名保持 app_id（历史遗留）', ''),
    (r'V3 架构中保持兼容，通过注释说明语义。', ''),
    (r'        \n        Note:\n.*?\n        """\n', '        """\n'),
]

# 需要处理的文件
FILES = [
    "gateway-api/src/interfaces/http/middleware/app_key.py",
    "gateway-api/src/interfaces/http/middleware/decision_rate_limit.py",
    "gateway-api/src/interfaces/http/v2/sdk.py",
    "gateway-api/src/interfaces/http/v2/challenge.py",
    "gateway-api/src/interfaces/http/v2/decide.py",
    "gateway-api/src/interfaces/http/v2/rule_test.py",
    "admin-api/src/interfaces/http/v2/access_logs.py",
    "admin-api/src/interfaces/http/v2/analytics.py",
    "admin-api/src/infrastructure/clickhouse/analytics_query.py",
]

def clean_file(filepath: Path):
    """清理单个文件"""
    if not filepath.exists():
        print(f"⚠️  文件不存在: {filepath}")
        return
    
    content = filepath.read_text(encoding='utf-8')
    original = content
    
    for pattern, replacement in PATTERNS:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        filepath.write_text(content, encoding='utf-8')
        print(f"✅ 已清理: {filepath}")
    else:
        print(f"⏭️  无需修改: {filepath}")

def main():
    root = Path(__file__).parent.parent
    print(f"工作目录: {root}\n")
    
    for file_path in FILES:
        clean_file(root / file_path)
    
    print("\n✅ 所有文件处理完成")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""完整的 app_id → site_id 重命名重构脚本"""
import re
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).parent.parent

# ============================================================================
# 阶段 1: 修改 shared schemas
# ============================================================================

SHARED_SCHEMAS_CHANGES = [
    # clock.py
    ("shared/src/fangyu_shared/schemas/clock.py", [
        (r'app_id: int = Field\(\.\.\., alias="appId"', 'site_id: int = Field(..., alias="siteId"'),
        (r'"""站点 ID。``0`` 表示全局阈值', '"""站点 ID。``0`` 表示全局阈值'),
        (r'def default_limits\(app_id: int\)', 'def default_limits(site_id: int)'),
        (r'return ClockLimits\(appId=app_id\)', 'return ClockLimits(siteId=site_id)'),
    ]),
    
    # event.py
    ("shared/src/fangyu_shared/schemas/event.py", [
        (r'app_id: int = Field\(\.\.\., alias="appId"', 'site_id: int = Field(..., alias="siteId"'),
    ]),
    
    # rule.py
    ("shared/src/fangyu_shared/schemas/rule.py", [
        (r'app_id: int = Field\(default=0, alias="appId"', 'site_id: int = Field(default=0, alias="siteId"'),
        (r'app_id: int = Field\(\.\.\., alias="appId"', 'site_id: int = Field(..., alias="siteId"'),
    ]),
]

# ============================================================================
# 阶段 2: 修改 Redis 键格式
# ============================================================================

REDIS_KEY_CHANGES = [
    # rule_cache.py
    ("admin-api/src/infrastructure/cache/rule_cache.py", [
        (r'fangyu:rules:app:\{app_id\}', 'fangyu:rules:site:{site_id}'),
        (r'app_id: int', 'site_id: int'),
        (r'self\._prefix \+ str\(app_id\)', 'self._prefix + str(site_id)'),
    ]),
    
    # AppCredential 类已经保留 app_id 字段名（为了兼容 Redis 存储格式）
    # 但需要添加注释说明这实际是 site_id
]

# ============================================================================
# 阶段 3: 修改 Gateway 中的 context.app_id
# ============================================================================

GATEWAY_CONTEXT_CHANGES = [
    ("gateway-api/src/interfaces/http/v2/decide.py", [
        (r'update=\{"app_id": resolved\.site_id\}', 'update={"site_id": resolved.site_id}'),
    ]),
]

# ============================================================================
# 执行函数
# ============================================================================

def apply_changes(file_path: str, replacements: List[Tuple[str, str]]):
    """应用替换到文件"""
    full_path = ROOT / file_path
    if not full_path.exists():
        print(f"⚠️  文件不存在: {file_path}")
        return
    
    content = full_path.read_text(encoding='utf-8')
    original = content
    
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        full_path.write_text(content, encoding='utf-8')
        print(f"✅ {file_path}")
    else:
        print(f"⏭️  {file_path}")

def main():
    print("=" * 70)
    print("完整的 app_id → site_id 重构")
    print("=" * 70)
    
    print("\n阶段 1: Shared Schemas")
    print("-" * 70)
    for file_path, replacements in SHARED_SCHEMAS_CHANGES:
        apply_changes(file_path, replacements)
    
    print("\n阶段 2: Redis 键格式")
    print("-" * 70)
    for file_path, replacements in REDIS_KEY_CHANGES:
        apply_changes(file_path, replacements)
    
    print("\n阶段 3: Gateway Context")
    print("-" * 70)
    for file_path, replacements in GATEWAY_CONTEXT_CHANGES:
        apply_changes(file_path, replacements)
    
    print("\n" + "=" * 70)
    print("✅ 重构脚本执行完成")
    print("=" * 70)
    print("\n后续手动步骤:")
    print("1. 修改数据库迁移脚本中的列名")
    print("2. 更新前端 SDK 配置参数")
    print("3. 运行测试: pytest")
    print("4. 提交代码: git commit -m 'refactor: rename app_id to site_id'")

if __name__ == "__main__":
    main()

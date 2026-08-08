#!/usr/bin/env python3
"""最终批量修复脚本 - 处理所有遗漏的 app_id"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# 需要完全重命名的文件（app_id → site_id）
FULL_RENAME_FILES = [
    # Gateway SDK endpoints
    "gateway-api/src/interfaces/http/v2/sdk.py",
    "gateway-api/src/interfaces/http/v2/challenge.py",
    
    # Admin API schemas
    "admin-api/src/interfaces/http/v2/schemas.py",
    "admin-api/src/interfaces/http/v2/sites.py",
]

# 需要保留但添加注释的文件（保留 app_id 用于兼容）
KEEP_WITH_COMMENT_FILES = [
    "gateway-api/src/interfaces/http/middleware/app_key.py",
    "gateway-api/src/application/services/decision_service.py",
]

def rename_field_definitions(content: str) -> str:
    """重命名字段定义"""
    # app_id: int = Field(..., alias="appId") → site_id: int = Field(..., alias="siteId")
    content = re.sub(
        r'app_id: int = Field\((.*?), alias="appId"(.*?)\)',
        r'site_id: int = Field(\1, alias="siteId"\2)',
        content
    )
    
    # payload.app_id → payload.site_id
    content = re.sub(r'\bpayload\.app_id\b', 'payload.site_id', content)
    
    # request.app_id → request.site_id
    content = re.sub(r'\brequest\.app_id\b', 'request.site_id', content)
    
    return content

def main():
    print("=" * 70)
    print("最终批量修复 - 处理所有遗漏的 app_id")
    print("=" * 70)
    
    for file_path in FULL_RENAME_FILES:
        full_path = ROOT / file_path
        if not full_path.exists():
            print(f"⚠️  文件不存在: {file_path}")
            continue
        
        content = full_path.read_text(encoding='utf-8')
        original = content
        
        # 执行重命名
        content = rename_field_definitions(content)
        
        if content != original:
            full_path.write_text(content, encoding='utf-8')
            print(f"✅ {file_path}")
        else:
            print(f"⏭️  {file_path}")
    
    print("\n" + "=" * 70)
    print("✅ 批量修复完成")
    print("=" * 70)

if __name__ == "__main__":
    main()

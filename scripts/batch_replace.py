#!/usr/bin/env python3
"""批量替换脚本 - 完成所有剩余的 app_id → site_id 重命名"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent

def run_grep_replace(pattern: str, replacement: str, file_pattern: str = "*.py"):
    """使用 PowerShell 执行批量替换"""
    ps_cmd = f"""
    Get-ChildItem -Recurse -Include {file_pattern} | ForEach-Object {{
        $content = Get-Content $_.FullName -Raw -Encoding UTF8
        $newContent = $content -replace '{pattern}', '{replacement}'
        if ($content -ne $newContent) {{
            [System.IO.File]::WriteAllText($_.FullName, $newContent, [System.Text.UTF8Encoding]::new($false))
            Write-Host "✅ $($_.FullName)"
        }}
    }}
    """
    subprocess.run(["powershell", "-Command", ps_cmd], cwd=ROOT)

def main():
    print("🔄 开始批量替换...")
    
    # 基本替换
    replacements = [
        (r'alias="appId"', r'alias="siteId"'),
        (r'aliasappId', r'alias="siteId"'),  # 修复可能的错误
    ]
    
    for pattern, replacement in replacements:
        print(f"\n替换: {pattern} → {replacement}")
        run_grep_replace(pattern, replacement)
    
    print("\n✅ 批量替换完成！")
    print("\n下一步:")
    print("1. 运行测试: pytest")
    print("2. 检查 git diff")
    print("3. 提交代码")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
修复 nginx.conf，添加 Lua 模块配置
通过 1Panel API 和容器内命令实现
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fangyu_scripts import OnePanelAPIClient, ContainerManager, Logger, Colors


def main():
    """主函数"""
    PANEL_URL = "http://198.200.42.128:31384"
    PANEL_KEY = "QWTbIertpeww14SeUXOrAsVerB1zCQUW"
    
    print(f"{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}修复 nginx.conf - 添加 Lua 模块配置{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}")
    print()
    
    # 初始化
    api = OnePanelAPIClient(PANEL_URL, PANEL_KEY)
    container_mgr = ContainerManager(api)
    
    # 查找容器
    Logger.step("1. 查找 OpenResty 容器...")
    container_name, container_id = container_mgr.find_openresty_container()
    print()
    
    # 读取当前 nginx.conf
    Logger.step("2. 读取当前 nginx.conf...")
    nginx_conf_path = "/usr/local/openresty/nginx/conf/nginx.conf"
    content = api.get_container_file_content(container_id, nginx_conf_path)
    
    if not content:
        Logger.error("无法读取 nginx.conf")
        sys.exit(1)
    
    Logger.success(f"已读取 nginx.conf ({len(content)} 字节)")
    print()
    
    # 检查是否已有 Lua 配置
    if 'lua_package_path' in content:
        Logger.success("✓ nginx.conf 已包含 Lua 配置，无需修复")
        sys.exit(0)
    
    Logger.warning("✗ nginx.conf 缺少 Lua 配置")
    print()
    
    # 修改配置
    Logger.step("3. 注入 Lua 模块配置...")
    
    lines = content.split('\n')
    new_lines = []
    injected = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # 在 http { 后的第一行插入
        if not injected and line.strip().startswith('http {'):
            new_lines.append('')
            new_lines.append('    # Lua 模块配置（Fangyu Defense 必需）')
            new_lines.append('    lua_package_path "/usr/local/openresty/lualib/?.lua;;";')
            new_lines.append('    lua_package_cpath "/usr/local/openresty/lualib/?.so;;";')
            new_lines.append('    lua_code_cache on;')
            new_lines.append('')
            injected = True
            Logger.success("✓ 已注入 Lua 配置")
    
    if not injected:
        Logger.error("✗ 未找到 http { 块，无法注入")
        sys.exit(1)
    
    new_content = '\n'.join(new_lines)
    print()
    
    # 写入本地临时文件
    Logger.step("4. 写入本地临时文件...")
    import tempfile
    temp_dir = Path(tempfile.gettempdir())
    local_temp_file = temp_dir / "nginx.conf.fixed"
    
    try:
        with open(local_temp_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        Logger.success(f"✓ 已写入临时文件: {local_temp_file}")
        print()
        
        # 上传到容器
        Logger.step("5. 上传到容器...")
        success = api.upload_file_to_container(
            container_id,
            str(local_temp_file),
            "/usr/local/openresty/nginx/conf"
        )
        
        if not success:
            Logger.error("✗ 上传失败")
            print()
            print(f"{Colors.YELLOW}{'='*70}{Colors.END}")
            print(f"{Colors.YELLOW}⚠ 自动上传失败，请手动修复{Colors.END}")
            print(f"{Colors.YELLOW}{'='*70}{Colors.END}")
            print()
            print(f"修改后的配置已保存到: {local_temp_file}")
            print()
            print("手动操作步骤:")
            print(f"  1. 通过 1Panel 文件管理器访问容器")
            print(f"  2. 备份原文件: /usr/local/openresty/nginx/conf/nginx.conf")
            print(f"  3. 上传新文件覆盖原文件")
            print(f"  4. 在容器内执行: nginx -t")
            print(f"  5. 在容器内执行: nginx -s reload")
            sys.exit(1)
        
        Logger.success("✓ 文件已上传到容器")
        print()
        
        print(f"{Colors.GREEN}{'='*70}{Colors.END}")
        print(f"{Colors.GREEN}✅ nginx.conf 已更新{Colors.END}")
        print(f"{Colors.GREEN}{'='*70}{Colors.END}")
        print()
        print("⚠ 重要：文件已上传到 /usr/local/openresty/nginx/conf/nginx.conf.fixed")
        print()
        print("需要手动完成以下步骤:")
        print("  1. 通过 1Panel 进入容器终端")
        print("  2. 备份: cp /usr/local/openresty/nginx/conf/nginx.conf /usr/local/openresty/nginx/conf/nginx.conf.backup")
        print("  3. 测试: nginx -t -c /usr/local/openresty/nginx/conf/nginx.conf.fixed")
        print("  4. 应用: mv /usr/local/openresty/nginx/conf/nginx.conf.fixed /usr/local/openresty/nginx/conf/nginx.conf")
        print("  5. 重载: nginx -s reload")
        print()
        print("或者直接在 1Panel 文件管理器中:")
        print("  1. 备份 nginx.conf")
        print("  2. 将 nginx.conf.fixed 重命名为 nginx.conf 覆盖原文件")
        print("  3. 在容器管理中重启 Nginx")
        
    except Exception as e:
        Logger.error(f"修复失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 不删除临时文件，方便用户手动操作
        pass


if __name__ == "__main__":
    main()

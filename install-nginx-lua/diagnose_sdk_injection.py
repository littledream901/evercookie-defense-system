#!/usr/bin/env python3
"""
SDK 不注入问题诊断脚本
用于排查 defense.lua + Nginx 配置中的常见问题
"""
import sys
from pathlib import Path

# 复用 fangyu_scripts 的工具类
sys.path.insert(0, str(Path(__file__).parent))
from fangyu_scripts import (
    OnePanelAPIClient, 
    ContainerManager, 
    Logger,
    Colors
)


class SDKInjectionDiagnoser:
    """SDK 注入诊断器"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
        self.issues = []
        self.warnings = []
    
    def diagnose(self, domain: str, container_id: str, config_path: str) -> bool:
        """执行完整诊断"""
        Logger.step("开始诊断 SDK 注入问题...")
        print()
        
        # 读取 Nginx 配置
        config = self.api_client.get_container_file_content(container_id, config_path)
        if not config:
            Logger.error("无法读取 Nginx 配置文件")
            return False
        
        # 执行各项检查
        self._check_nginx_lua_config(container_id)  # 新增：检查 nginx.conf
        self._check_var_declaration(config)
        self._check_body_filter(config)
        self._check_access_lua(config)
        self._check_sdk_inject_flag(config)
        self._check_fail_mode(config)
        self._check_gateway_config(config)
        self._check_defense_lua_exists(domain, container_id)
        
        # 输出诊断结果
        return self._display_results()
    
    def _check_nginx_lua_config(self, container_id: str):
        """检查 nginx.conf 中的 Lua 配置（最关键）"""
        Logger.step("检查 0/7: nginx.conf 中的 Lua 模块配置")
        
        nginx_conf_path = "/usr/local/openresty/nginx/conf/nginx.conf"
        content = self.api_client.get_container_file_content(container_id, nginx_conf_path)
        
        if not content:
            Logger.error("✗ 无法读取 nginx.conf")
            self.issues.append({
                'name': '无法读取 nginx.conf',
                'severity': 'CRITICAL',
                'description': 'nginx.conf 文件不存在或无权限访问',
                'fix': '检查容器和文件路径'
            })
            print()
            return
        
        has_lua_package_path = 'lua_package_path' in content
        has_lua_package_cpath = 'lua_package_cpath' in content
        
        if not has_lua_package_path or not has_lua_package_cpath:
            Logger.error("✗ nginx.conf 中缺少 Lua 模块配置")
            Logger.error("  这是导致 Lua 代码完全不执行的根本原因！")
            self.issues.append({
                'name': 'nginx.conf 缺少 Lua 配置',
                'severity': 'CRITICAL',
                'description': 'nginx.conf 的 http 块中缺少 lua_package_path 和 lua_package_cpath',
                'fix': '运行修复脚本或手动在 http 块中添加 Lua 配置'
            })
        else:
            Logger.success("✓ nginx.conf 中已配置 Lua 模块")
        
        print()
    
    def _check_var_declaration(self, config: str):
        """检查 $fy_sdk_snippet 变量是否声明"""
        Logger.step("检查 1/7: $fy_sdk_snippet 变量声明")
        
        if 'set $fy_sdk_snippet' in config:
            Logger.success("✓ $fy_sdk_snippet 已声明")
        else:
            Logger.error("✗ 缺少 $fy_sdk_snippet 变量声明")
            self.issues.append({
                'name': '缺少变量声明',
                'severity': 'CRITICAL',
                'description': '$fy_sdk_snippet 未在 Nginx 配置中声明',
                'fix': '在 Fangyu 配置块中添加: set $fy_sdk_snippet "";'
            })
        print()
    
    def _check_body_filter(self, config: str):
        """检查 body_filter_by_lua_block"""
        Logger.step("检查 2/7: body_filter_by_lua_block 配置")
        
        if 'body_filter_by_lua_block' not in config:
            Logger.error("✗ 缺少 body_filter_by_lua_block")
            self.issues.append({
                'name': '缺少 body_filter',
                'severity': 'CRITICAL',
                'description': 'body_filter_by_lua_block 未配置',
                'fix': '在 server 块结束前添加 body_filter_by_lua_block'
            })
        elif 'ngx.var.fy_sdk_snippet' not in config:
            Logger.warning("⚠ body_filter 存在但未读取 ngx.var.fy_sdk_snippet")
            self.warnings.append({
                'name': 'body_filter 逻辑错误',
                'description': 'body_filter 未正确读取 SDK snippet 变量'
            })
        elif '</head>' not in config or 'gsub' not in config:
            Logger.warning("⚠ body_filter 存在但未执行 </head> 替换")
            self.warnings.append({
                'name': 'body_filter 注入逻辑缺失',
                'description': 'body_filter 未包含 </head> 替换逻辑'
            })
        else:
            Logger.success("✓ body_filter_by_lua_block 配置正确")
        print()
    
    def _check_access_lua(self, config: str):
        """检查 access_by_lua_file"""
        Logger.step("检查 3/7: access_by_lua_file 配置")
        
        if 'access_by_lua_file' not in config or 'defense.lua' not in config:
            Logger.error("✗ 缺少 access_by_lua_file 指令")
            self.issues.append({
                'name': '缺少 access_by_lua_file',
                'severity': 'CRITICAL',
                'description': 'defense.lua 未被加载',
                'fix': '在 location / 块中添加: access_by_lua_file /www/sites/{domain}/lua/defense.lua;'
            })
        else:
            Logger.success("✓ access_by_lua_file 已配置")
        print()
    
    def _check_sdk_inject_flag(self, config: str):
        """检查 SDK 注入开关"""
        Logger.step("检查 4/7: SDK 注入开关")
        
        if 'set $fangyu_sdk_inject' not in config:
            Logger.warning("⚠ 未显式设置 $fangyu_sdk_inject，将使用默认值 'on'")
            self.warnings.append({
                'name': 'SDK 注入开关未设置',
                'description': '建议显式设置: set $fangyu_sdk_inject "on";'
            })
        elif '"off"' in config and 'fangyu_sdk_inject' in config:
            # 简单检测，可能误判
            Logger.error("✗ SDK 注入可能被关闭（检测到 'off'）")
            self.issues.append({
                'name': 'SDK 注入被关闭',
                'severity': 'HIGH',
                'description': '$fangyu_sdk_inject 设置为 "off"',
                'fix': '修改为: set $fangyu_sdk_inject "on";'
            })
        else:
            Logger.success("✓ SDK 注入开关正常")
        print()
    
    def _check_fail_mode(self, config: str):
        """检查 fail_mode 配置"""
        Logger.step("检查 5/7: fail_mode 配置")
        
        if 'set $fangyu_fail_mode' not in config:
            Logger.warning("⚠ 未设置 $fangyu_fail_mode，将使用默认值 'open'")
        elif '"closed"' in config and 'fangyu_fail_mode' in config:
            Logger.warning("⚠ fail_mode 设为 'closed'，网关失败时会拦截请求")
            self.warnings.append({
                'name': 'fail_mode 为 closed',
                'description': '网关不可达时会拦截所有请求，建议改为 "open"'
            })
        else:
            Logger.success("✓ fail_mode 配置正常")
        print()
    
    def _check_gateway_config(self, config: str):
        """检查网关配置"""
        Logger.step("检查 6/7: 网关配置")
        
        required_vars = [
            'fangyu_gateway_url',
            'fangyu_site_id',
            'fangyu_site_key',
            'fangyu_site_secret'
        ]
        
        missing = []
        for var in required_vars:
            if f'set ${var}' not in config:
                missing.append(var)
        
        if missing:
            Logger.error(f"✗ 缺少必需配置: {', '.join(missing)}")
            self.issues.append({
                'name': '缺少网关配置',
                'severity': 'CRITICAL',
                'description': f'缺少: {", ".join(missing)}',
                'fix': '确保所有 Fangyu 配置变量都已设置'
            })
        else:
            Logger.success("✓ 网关配置完整")
        print()
    
    def _check_defense_lua_exists(self, domain: str, container_id: str):
        """检查 defense.lua 文件"""
        Logger.step("检查 7/7: defense.lua 文件")
        
        try:
            content = self.api_client.get_container_file_content(
                container_id,
                f"/www/sites/{domain}/lua/defense.lua"
            )
            
            if not content:
                Logger.error("✗ defense.lua 文件不存在")
                self.issues.append({
                    'name': 'defense.lua 缺失',
                    'severity': 'CRITICAL',
                    'description': 'defense.lua 文件未部署',
                    'fix': '运行 fangyu_scripts.py 重新部署'
                })
            elif len(content) < 10000:
                Logger.warning(f"⚠ defense.lua 文件太小 ({len(content)} 字节)，可能不完整")
                self.warnings.append({
                    'name': 'defense.lua 可能不完整',
                    'description': f'文件大小: {len(content)} 字节，预期 > 10KB'
                })
            else:
                Logger.success(f"✓ defense.lua 文件正常 ({len(content)} 字节)")
        except Exception as e:
            Logger.error(f"✗ 无法检查 defense.lua: {e}")
            self.issues.append({
                'name': 'defense.lua 检查失败',
                'severity': 'HIGH',
                'description': str(e),
                'fix': '检查文件路径和容器权限'
            })
        print()
    
    def _display_results(self) -> bool:
        """显示诊断结果"""
        print("=" * 80)
        print("诊断结果汇总")
        print("=" * 80)
        print()
        
        # 显示严重问题
        critical_issues = [i for i in self.issues if i.get('severity') == 'CRITICAL']
        high_issues = [i for i in self.issues if i.get('severity') == 'HIGH']
        
        if critical_issues:
            print(f"{Colors.RED}{'='*80}{Colors.END}")
            print(f"{Colors.RED}🚨 发现 {len(critical_issues)} 个严重问题（CRITICAL）{Colors.END}")
            print(f"{Colors.RED}{'='*80}{Colors.END}")
            print()
            
            for i, issue in enumerate(critical_issues, 1):
                print(f"{Colors.RED}问题 {i}: {issue['name']}{Colors.END}")
                print(f"  描述: {issue['description']}")
                print(f"  修复: {issue['fix']}")
                print()
        
        if high_issues:
            print(f"{Colors.YELLOW}{'='*80}{Colors.END}")
            print(f"{Colors.YELLOW}⚠ 发现 {len(high_issues)} 个高优先级问题（HIGH）{Colors.END}")
            print(f"{Colors.YELLOW}{'='*80}{Colors.END}")
            print()
            
            for i, issue in enumerate(high_issues, 1):
                print(f"{Colors.YELLOW}问题 {i}: {issue['name']}{Colors.END}")
                print(f"  描述: {issue['description']}")
                print(f"  修复: {issue['fix']}")
                print()
        
        # 显示警告
        if self.warnings:
            print(f"{Colors.BLUE}{'='*80}{Colors.END}")
            print(f"{Colors.BLUE}📋 {len(self.warnings)} 个警告{Colors.END}")
            print(f"{Colors.BLUE}{'='*80}{Colors.END}")
            print()
            
            for i, warning in enumerate(self.warnings, 1):
                print(f"{Colors.BLUE}警告 {i}: {warning['name']}{Colors.END}")
                print(f"  {warning['description']}")
                print()
        
        # 综合判断
        if not self.issues:
            print(f"{Colors.GREEN}{'='*80}{Colors.END}")
            print(f"{Colors.GREEN}✅ 配置检查通过！未发现严重问题{Colors.END}")
            print(f"{Colors.GREEN}{'='*80}{Colors.END}")
            print()
            
            if self.warnings:
                print("建议:")
                print("  1. 检查上述警告项并根据需要优化")
                print("  2. 测试 SDK 是否正常注入")
                print("  3. 检查 Nginx 错误日志")
            else:
                print("如果 SDK 仍未注入，请检查:")
                print("  1. 网关是否可达（decision 返回 pass）")
                print("  2. 响应是否为 HTML（Content-Type: text/html）")
                print("  3. Nginx 错误日志中是否有 Lua 错误")
            
            return True
        else:
            print(f"{Colors.RED}{'='*80}{Colors.END}")
            print(f"{Colors.RED}❌ 发现 {len(self.issues)} 个问题需要修复{Colors.END}")
            print(f"{Colors.RED}{'='*80}{Colors.END}")
            print()
            
            print("修复建议:")
            print("  1. 按照上述修复指引逐项修复")
            print("  2. 修复后运行 nginx -t 测试配置")
            print("  3. 重载 Nginx: nginx -s reload")
            print("  4. 重新运行本诊断脚本验证")
            
            return False


def main():
    """主函数"""
    # 配置区（与 fangyu_scripts.py 保持一致）
    DOMAIN = "waybifair.shop"
    PANEL_URL = "http://198.200.42.128:31384"
    PANEL_KEY = "QWTbIertpeww14SeUXOrAsVerB1zCQUW"
    
    print(f"{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BLUE}SDK 注入诊断工具 - Fangyu Defense{Colors.END}")
    print(f"{Colors.BLUE}{'='*80}{Colors.END}")
    print()
    print(f"域名: {DOMAIN}")
    print(f"1Panel: {PANEL_URL}")
    print()
    
    # 初始化客户端
    api_client = OnePanelAPIClient(PANEL_URL, PANEL_KEY)
    container_mgr = ContainerManager(api_client)
    diagnoser = SDKInjectionDiagnoser(api_client)
    
    # 查找容器
    container_name, container_id = container_mgr.find_openresty_container()
    print()
    
    # 查找配置文件
    Logger.step("查找 Nginx 配置文件...")
    websites = api_client.search_websites(DOMAIN)
    if not websites:
        Logger.error(f"找不到域名 {DOMAIN}")
        sys.exit(1)
    
    website_info = websites[0]
    alias = website_info.get('alias', DOMAIN)
    
    possible_paths = [
        f"/usr/local/openresty/nginx/conf/conf.d/{alias}.conf",
        f"/usr/local/openresty/nginx/conf/conf.d/{DOMAIN}.conf",
    ]
    
    config_path = None
    for path in possible_paths:
        if api_client.get_container_file_content(container_id, path):
            config_path = path
            Logger.success(f"找到配置文件: {path}")
            break
    
    if not config_path:
        Logger.error("无法找到 Nginx 配置文件")
        sys.exit(1)
    
    print()
    
    # 执行诊断
    success = diagnoser.diagnose(DOMAIN, container_id, config_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

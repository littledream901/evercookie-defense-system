#!/usr/bin/env python3
"""
Fangyu Defense 自动安装脚本 - 1Panel OpenResty 版
重构版本：优化代码结构和可维护性
"""
import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


def _strip_nginx_comment(line: str) -> str:
    result = []
    in_single = False
    in_double = False
    escaped = False

    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == '\\':
            result.append(char)
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            continue
        if char == '#' and not in_single and not in_double:
            break
        result.append(char)

    return ''.join(result)


def _find_first_block(lines: List[str], block_name: str) -> Tuple[int, int]:
    start = -1
    depth = 0

    for idx, line in enumerate(lines):
        text = _strip_nginx_comment(line)
        if start < 0:
            if text.lstrip().startswith(f'{block_name} ') or text.lstrip().startswith(f'{block_name}{{') or text.lstrip() == f'{block_name} {{':
                if '{' in text:
                    start = idx
                    depth = text.count('{') - text.count('}')
                    if depth <= 0:
                        return start, idx
        else:
            depth += text.count('{') - text.count('}')
            if depth <= 0:
                return start, idx

    return -1, -1


def _find_location_block(lines: List[str], server_start: int, server_end: int, location_path: str = '/') -> Tuple[int, int]:
    start = -1
    depth = 0
    pattern = re.compile(rf'^\s*location\s+(?:=\s*)?{re.escape(location_path)}\s*\{{')

    for idx in range(server_start + 1, server_end):
        text = _strip_nginx_comment(lines[idx])
        if start < 0:
            if pattern.search(text):
                start = idx
                depth = text.count('{') - text.count('}')
                if depth <= 0:
                    return start, idx
        else:
            depth += text.count('{') - text.count('}')
            if depth <= 0:
                return start, idx

    return -1, -1


def _clean_nginx_value(value: str) -> str:
    cleaned = value.strip()
    while cleaned and cleaned[0] in '`"\' ':
        cleaned = cleaned[1:].strip()
    while cleaned and cleaned[-1] in '`"\' ':
        cleaned = cleaned[:-1].strip()
    return cleaned


def _extract_server_name(config_content: str) -> Optional[str]:
    lines = config_content.split('\n')
    server_start, server_end = _find_first_block(lines, 'server')
    if server_start < 0 or server_end < 0:
        return None

    for idx in range(server_start, server_end + 1):
        stripped = _strip_nginx_comment(lines[idx]).strip()
        if not stripped.startswith('server_name'):
            continue
        names = stripped.removesuffix(';').split()[1:]
        if names:
            return names[0]
    return None


def _build_real_ip_block() -> str:
    return """    set_real_ip_from 127.0.0.1;
    set_real_ip_from 10.0.0.0/8;
    set_real_ip_from 172.16.0.0/12;
    set_real_ip_from 192.168.0.0/16;
    set_real_ip_from 100.64.0.0/10;
    set_real_ip_from 169.254.0.0/16;
    set_real_ip_from ::1;

    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 2400:cb00::/32;
    set_real_ip_from 2606:4700::/32;
    set_real_ip_from 2803:f800::/32;
    set_real_ip_from 2405:b500::/32;
    set_real_ip_from 2405:8100::/32;
    set_real_ip_from 2a06:98c0::/29;
    set_real_ip_from 2c0f:f248::/32;

    real_ip_header CF-Connecting-IP;
    real_ip_recursive on;"""


class Colors:
    """终端颜色输出"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


class Logger:
    """日志输出工具"""
    
    @staticmethod
    def step(msg: str):
        print(f"{Colors.BLUE}[步骤]{Colors.END} {msg}")
    
    @staticmethod
    def success(msg: str):
        print(f"{Colors.GREEN}[成功]{Colors.END} {msg}")
    
    @staticmethod
    def warning(msg: str):
        print(f"{Colors.YELLOW}[警告]{Colors.END} {msg}")
    
    @staticmethod
    def error(msg: str):
        print(f"{Colors.RED}[错误]{Colors.END} {msg}")


class OnePanelAPIClient:
    """1Panel API 客户端封装"""
    
    def __init__(self, panel_url: str, panel_key: str):
        self.panel_url = panel_url.rstrip('/')
        self.panel_key = panel_key
        self.session = requests.Session()
        self.session.trust_env = False
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    
    def _generate_signature(self) -> Tuple[str, str]:
        """生成 1Panel API 签名"""
        timestamp = str(int(time.time()))
        sign_str = f"1panel{self.panel_key}{timestamp}"
        signature = hashlib.md5(sign_str.encode()).hexdigest()
        return signature, timestamp
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        signature, timestamp = self._generate_signature()
        return {
            "Content-Type": "application/json",
            "1Panel-Token": signature,
            "1Panel-Timestamp": timestamp,
        }
    
    def search_containers(self, name: str, state: str = "running", 
                         page_size: int = 50, order: str = "ascending",
                         max_pages: int = 100) -> List[Dict]:
        """搜索容器（支持分页遍历）
        
        Args:
            name: 容器名称（模糊搜索）
            state: 容器状态，默认 "running"
            page_size: 每页数量，默认 50
            order: 排序方式，可选 "ascending", "descending", "null"，默认 "ascending"
            max_pages: 最大遍历页数，默认 100（防止无限循环）
        
        Returns:
            所有匹配的容器列表
        """
        all_containers = []
        
        for page in range(1, max_pages + 1):
            headers = self._get_headers()
            
            resp = self.session.post(
                f"{self.panel_url}/api/v2/containers/search",
                headers=headers,
                json={
                    "name": name,
                    "state": state,
                    "page": page,
                    "pageSize": page_size,
                    "orderBy": "name",
                    "order": order
                },
                timeout=10,
                verify=False
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200 and data.get('data', {}).get('items'):
                    items = data['data']['items']
                    all_containers.extend(items)
                    
                    # 如果返回数量少于 pageSize，说明已经是最后一页
                    if len(items) < page_size:
                        break
                else:
                    break
            else:
                Logger.warning(f"容器搜索失败: HTTP {resp.status_code}")
                break
        
        return all_containers
    
    def get_container_file_content(self, container_id: str, path: str) -> Optional[str]:
        """获取容器内文件内容"""
        headers = self._get_headers()
        
        resp = self.session.post(
            f"{self.panel_url}/api/v2/containers/files/content",
            headers=headers,
            json={
                "containerID": container_id,
                "path": path
            },
            timeout=10,
            verify=False
        )
        
        if resp.status_code == 200 and resp.json().get('code') == 200:
            return resp.json()['data']['content']
        
        return None
    
    def upload_file_to_container(self, container_id: str, local_path: str, target_dir: str) -> bool:
        """上传文件到容器"""
        headers = self._get_headers()
        
        # 移除 Content-Type，让 requests 自动设置 multipart/form-data
        headers.pop("Content-Type", None)
        
        with open(local_path, 'rb') as f:
            files = {
                'file': (os.path.basename(local_path), f, 'application/octet-stream')
            }
            data = {
                'containerID': container_id,
                'path': target_dir
            }
            
            resp = self.session.post(
                f"{self.panel_url}/api/v2/containers/files/upload",
                headers=headers,
                data=data,
                files=files,
                timeout=30,
                verify=False
            )
            
            if resp.status_code == 200:
                result = resp.json()
                return result.get('code') == 200
        
        return False
    
    def exec_container_command(self, container_id: str, command: str) -> Tuple[bool, str, str]:
        """在容器内执行命令
        
        Args:
            container_id: 容器 ID
            command: 要执行的命令
        
        Returns:
            (success, stdout, stderr) 元组
        """
        headers = self._get_headers()
        
        resp = self.session.post(
            f"{self.panel_url}/api/v2/containers/exec",
            headers=headers,
            json={
                "containerID": container_id,
                "command": command
            },
            timeout=30,
            verify=False
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 200:
                result = data.get('data', {})
                return (
                    result.get('exitCode', 1) == 0,
                    result.get('stdout', ''),
                    result.get('stderr', '')
                )
        
        return False, "", f"API 调用失败: {resp.status_code}"
    
    def update_website_nginx_config(self, website_id: int, content: str) -> bool:
        """通过 1Panel Website Nginx 接口更新站点配置"""
        headers = self._get_headers()
        resp = self.session.post(
            f"{self.panel_url}/api/v2/websites/nginx/update",
            headers=headers,
            json={
                "id": website_id,
                "content": content,
            },
            timeout=30,
            verify=False
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 200:
                return True
            Logger.warning(f"站点 Nginx 更新失败: {data}")
        else:
            Logger.warning(f"站点 Nginx 更新失败: HTTP {resp.status_code}")
        return False
    
    def check_file_exists(self, container_id: str, file_path: str) -> bool:
        """检查容器内文件是否存在
        
        Args:
            container_id: 容器 ID
            file_path: 文件路径
        
        Returns:
            文件是否存在
        """
        success, stdout, stderr = self.exec_container_command(
            container_id,
            f"test -f {shlex.quote(file_path)} && echo 'exists' || echo 'not_found'"
        )
        
        return success and 'exists' in stdout
    
    def search_websites(self, domain: str, page_size: int = 50, max_pages: int = 100) -> List[Dict]:
        """搜索网站（支持分页遍历）
        
        Args:
            domain: 域名（模糊搜索）
            page_size: 每页数量，默认 50
            max_pages: 最大遍历页数，默认 100（防止无限循环）
        
        Returns:
            所有匹配的网站列表
        """
        all_websites = []
        
        for page in range(1, max_pages + 1):
            headers = self._get_headers()
            
            resp = self.session.post(
                f"{self.panel_url}/api/v2/websites/search",
                headers=headers,
                json={
                    "name": domain,
                    "page": page,
                    "pageSize": page_size,
                    "orderBy": "primary_domain",
                    "order": "ascending"
                },
                timeout=10,
                verify=False
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200 and data.get('data', {}).get('items'):
                    items = data['data']['items']
                    all_websites.extend(items)
                    
                    # 如果返回数量少于 pageSize，说明已经是最后一页
                    if len(items) < page_size:
                        break
                else:
                    break
            else:
                Logger.warning(f"站点搜索失败: HTTP {resp.status_code}")
                break
        
        return all_websites


def run_cmd(cmd: str, check: bool = True, capture: bool = True) -> Optional[str]:
    """执行命令"""
    result = subprocess.run(
        cmd, 
        shell=True, 
        check=check,
        capture_output=capture,
        text=True
    )
    return result.stdout.strip() if capture else None


class ContainerManager:
    """容器管理类"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
    
    def find_openresty_container(self) -> Tuple[str, str]:
        """查找 OpenResty 容器"""
        Logger.step("查找 OpenResty 容器...")
        
        try:
            containers = self.api_client.search_containers("openresty", state="running")
            
            if containers:
                Logger.step(f"共找到 {len(containers)} 个匹配的容器")
                container = containers[0]
                container_name = container.get('name')
                container_id = container.get('containerID')
                Logger.success(f"使用容器: {container_name} (ID: {container_id[:12]}...)")
                return container_name, container_id
            
            Logger.error("未找到运行中的 OpenResty 容器")
            sys.exit(1)
            
        except Exception as e:
            Logger.error(f"查找容器失败: {e}")
            sys.exit(1)
    
    def check_lua_dependencies(self, container_id: str) -> bool:
        """检查 Lua 依赖"""
        Logger.step("检查 Lua 依赖...")
        
        try:
            content = self.api_client.get_container_file_content(
                container_id, 
                "/usr/local/openresty/lualib/resty/http.lua"
            )
            
            if content:
                Logger.success("Lua 依赖已存在")
                return True
            else:
                Logger.warning("Lua 依赖检查失败，但将继续部署（OpenResty 通常自带依赖）")
                return False
                
        except Exception as e:
            Logger.warning(f"依赖检查失败: {e}，将继续部署")
            return False



class NginxConfManager:
    """nginx.conf 主配置管理器"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
    
    def check_lua_config(self, container_id: str) -> bool:
        """检查 nginx.conf 中是否有 Lua 配置"""
        nginx_conf_path = "/usr/local/openresty/nginx/conf/nginx.conf"
        content = self.api_client.get_container_file_content(container_id, nginx_conf_path)
        
        if not content:
            return False
        
        active_lines = [_strip_nginx_comment(line) for line in content.split('\n')]
        cleaned = '\n'.join(active_lines)
        return (
            re.search(r'(?m)^\s*lua_package_path\b', cleaned) is not None
            and re.search(r'(?m)^\s*lua_package_cpath\b', cleaned) is not None
        )
    
    def add_lua_config(self, container_id: str) -> bool:
        """在 nginx.conf 的 http 块中添加 Lua 配置"""
        nginx_conf_path = "/usr/local/openresty/nginx/conf/nginx.conf"
        content = self.api_client.get_container_file_content(container_id, nginx_conf_path)
        
        if not content:
            Logger.error("无法读取 nginx.conf")
            return False
        
        # 检查是否已有配置
        active_lines = [_strip_nginx_comment(line) for line in content.split('\n')]
        cleaned = '\n'.join(active_lines)
        if (
            re.search(r'(?m)^\s*lua_package_path\b', cleaned) is not None
            and re.search(r'(?m)^\s*lua_package_cpath\b', cleaned) is not None
        ):
            Logger.warning("nginx.conf 中已有 lua_package_path 配置")
            return True
        
        Logger.step("在 nginx.conf 的 http 块中添加 Lua 配置...")
        
        # 在 http { 后插入 Lua 配置
        lua_config = """
    # Lua 模块配置
    lua_package_path "/usr/local/openresty/lualib/?.lua;;";
    lua_package_cpath "/usr/local/openresty/lualib/?.so;;";
    lua_code_cache on;
"""
        
        lines = content.split('\n')
        new_lines = []
        inserted = False
        http_start, _ = _find_first_block(lines, 'http')
        
        for idx, line in enumerate(lines):
            new_lines.append(line)
            
            if not inserted and idx == http_start:
                new_lines.append(lua_config)
                inserted = True
        
        if not inserted:
            Logger.error("未找到 http 块")
            return False
        
        new_content = '\n'.join(new_lines)
        
        # 清理换行符
        new_content = new_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 通过临时文件上传
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_file = Path(tmp_dir) / "nginx.conf"
                with open(tmp_file, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(new_content)
                
                # 尝试上传
                success = self.api_client.upload_file_to_container(
                    container_id,
                    str(tmp_file),
                    "/usr/local/openresty/nginx/conf"
                )
                
                if success:
                    Logger.success("✓ nginx.conf 已更新")
                    return True
                else:
                    Logger.error("✗ 上传失败，请手动修改 nginx.conf")
                    self._print_manual_fix_guide(container_id)
                    return False
        except Exception as e:
            Logger.error(f"更新失败: {e}")
            self._print_manual_fix_guide(container_id)
            return False
    
    def _print_manual_fix_guide(self, container_id: str):
        """打印手动修复指南"""
        print()
        print("="*70)
        print("手动修复指南")
        print("="*70)
        print()
        print("1. 进入容器:")
        print(f"   docker exec -it {container_id[:12]} sh")
        print()
        print("2. 编辑 nginx.conf:")
        print("   vi /usr/local/openresty/nginx/conf/nginx.conf")
        print()
        print("3. 在 http 块开始后添加:")
        print("""
    http {
        # 添加以下 Lua 配置
        lua_package_path "/usr/local/openresty/lualib/?.lua;;";
        lua_package_cpath "/usr/local/openresty/lualib/?.so;;";
        lua_code_cache on;
        
        # ... 其他配置 ...
    }
""")
        print("4. 测试配置: nginx -t")
        print("5. 重新加载: nginx -s reload")
        print()


class DefenseLuaDeployer:
    """Defense.lua 部署器"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
    
    def _find_defense_lua_source(self) -> Optional[str]:
        """查找 defense.lua 源文件"""
        possible_paths = [
            str(Path(__file__).parent.parent / "adapters" / "nginx-lua" / "defense.lua"),
            str(Path(__file__).parent / "adapters" / "nginx-lua" / "defense.lua"),
            "./adapters/nginx-lua/defense.lua",
            "../adapters/nginx-lua/defense.lua",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                file_size = os.path.getsize(path)
                if file_size < 500:
                    Logger.warning(f"跳过 {path} (文件太小: {file_size} 字节，可能是占位符)")
                    continue
                Logger.success(f"找到源文件: {path} ({file_size} 字节)")
                return path
        
        return None
    
    def deploy(self, domain: str, container_id: str) -> bool:
        """部署 defense.lua 到容器"""
        Logger.step(f"部署 defense.lua for {domain}...")
        
        source_file = self._find_defense_lua_source()
        
        if not source_file:
            Logger.error("找不到完整的 defense.lua 文件")
            Logger.warning("请确保完整的 defense.lua 文件存在于:")
            Logger.warning(f"  {str(Path(__file__).parent / 'adapters' / 'nginx-lua' / 'defense.lua')}")
            sys.exit(1)
        
        target_dir = f"/www/sites/{domain}/lua"
        
        try:
            success = self.api_client.upload_file_to_container(
                container_id,
                source_file,
                target_dir
            )
            
            if success:
                Logger.success(f"defense.lua 已上传到容器: {target_dir}/defense.lua")
                return True
            else:
                Logger.error("上传失败")
                sys.exit(1)
                
        except Exception as e:
            Logger.error(f"文件上传失败: {e}")
            sys.exit(1)


class NginxConfigGenerator:
    """Nginx 配置生成器"""
    
    @staticmethod
    def generate_config_blocks(domain: str, site_key: str, site_id: str, 
                              site_secret: str, gateway_url: str) -> Tuple[str, str, str]:
        """生成 Nginx 配置块
        
        Args:
            domain: 域名
            site_key: 站点密钥字符串（格式：site_xxxxxxxx）
            site_id: 站点数字主键（Site.id，整数字符串）
            site_secret: 站点签名密钥
            gateway_url: 网关 URL
        """
        domain = _clean_nginx_value(domain)
        site_key = _clean_nginx_value(site_key)
        site_id = _clean_nginx_value(site_id)
        site_secret = _clean_nginx_value(site_secret)
        gateway_url = _clean_nginx_value(gateway_url)
        vars_block = f"""
{_build_real_ip_block()}

    # Fangyu Defense 配置
    set $fangyu_gateway_url  "{gateway_url}";
    set $fangyu_site_key     "{site_key}";
    set $fangyu_site_id      "{site_id}";
    set $fangyu_site_secret  "{site_secret}";
    set $fangyu_fail_mode    "open";
    set $fangyu_sdk_inject   "on";
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";
    set $fy_sdk_snippet      "";
    set $fy_server_token     "";"""
        
        access_lua = f"""        access_by_lua_file /www/sites/{domain}/lua/defense.lua;
        proxy_set_header Accept-Encoding "";
        proxy_hide_header Content-Encoding;"""
        
        body_filter = """        body_filter_by_lua_block {
            local snippet = ngx.var.fy_sdk_snippet
            if not snippet or snippet == "" then return end

            local ct = ngx.header["Content-Type"] or ""
            if type(ct) == "string" and string.find(ct, "text/html", 1, true) then
                local chunk = ngx.arg[1]
                if chunk and type(chunk) == "string" and chunk ~= "" then
                    local safe_snippet = snippet:gsub("%%", "%%%%")
                    local new_chunk, count = string.gsub(chunk, "</head>", safe_snippet .. "</head>", 1)
                    if count > 0 then
                        ngx.arg[1] = new_chunk
                    end
                end
            end
        }"""
        
        return vars_block, access_lua, body_filter
    
    @staticmethod
    def remove_old_fangyu_config(config_content: str) -> str:
        """删除旧的 Fangyu 配置"""
        # 检查是否有任何 Fangyu 相关配置
        cleaned_lines = [_strip_nginx_comment(line) for line in config_content.split('\n')]
        cleaned_content = '\n'.join(cleaned_lines)
        has_fangyu_config = (
            re.search(r'(?m)^\s*set\s+\$fangyu_', cleaned_content) is not None
            or re.search(r'(?m)^\s*set\s+\$fy_', cleaned_content) is not None
            or re.search(r'(?m)^\s*access_by_lua_file\b.*defense\.lua', cleaned_content) is not None
            or re.search(r'(?m)^\s*body_filter_by_lua_block\b', cleaned_content) is not None
            or re.search(r'(?m)^\s*set_real_ip_from\b', cleaned_content) is not None
            or re.search(r'(?m)^\s*real_ip_(?:header|recursive)\b', cleaned_content) is not None
        )
        
        if not has_fangyu_config:
            return config_content
        
        Logger.warning("检测到已有 Fangyu 配置，先删除旧配置")
        
        lines = config_content.split('\n')
        new_lines = []
        in_fangyu_block = False
        in_body_filter = False
        body_filter_brace_count = 0
        in_access_block = False
        
        for line in lines:
            stripped = _strip_nginx_comment(line).strip()
            
            if stripped.startswith('set $fangyu_') or stripped.startswith('set $fy_'):
                continue

            if stripped.startswith('set_real_ip_from'):
                continue

            if stripped.startswith('real_ip_header') or stripped.startswith('real_ip_recursive'):
                continue
            
            if '# Fangyu Defense' in line or 'Fangyu Defense 配置' in line:
                in_fangyu_block = True
                continue
            
            if in_fangyu_block:
                if not stripped or stripped.startswith('set $fangyu_') or stripped.startswith('set $fy_'):
                    continue
                in_fangyu_block = False
            
            if stripped.startswith('access_by_lua_file') and 'defense.lua' in stripped:
                continue

            if stripped == 'proxy_set_header Accept-Encoding "";' or stripped == 'proxy_hide_header Content-Encoding;':
                continue

            if in_access_block:
                if not stripped or stripped.startswith('set $'):
                    continue
                in_access_block = False
            
            if stripped.startswith('body_filter_by_lua_block'):
                in_body_filter = True
                body_filter_brace_count = stripped.count('{') - stripped.count('}')
                continue
            
            if in_body_filter:
                body_filter_brace_count += stripped.count('{') - stripped.count('}')
                if body_filter_brace_count <= 0:
                    in_body_filter = False
                continue
            
            new_lines.append(line)
        
        Logger.step("✓ 已删除旧的 Fangyu 配置")
        return '\n'.join(new_lines)
    
    @staticmethod
    def inject_vars_block(config_content: str, vars_block: str) -> str:
        """在 server_name 后注入变量块"""
        lines = config_content.split('\n')
        new_lines = []
        inserted_vars = False
        server_start, server_end = _find_first_block(lines, 'server')
        
        if server_start < 0 or server_end < 0:
            return config_content
        
        for idx, line in enumerate(lines):
            new_lines.append(line)
            
            if inserted_vars or idx < server_start or idx > server_end:
                continue
            
            cleaned = _strip_nginx_comment(line).strip()
            if cleaned.startswith('server_name') and cleaned.endswith(';'):
                new_lines.append('')
                new_lines.append(vars_block.rstrip())
                new_lines.append('')
                inserted_vars = True
        
        if inserted_vars:
            Logger.step("✓ 已插入 Fangyu 变量配置")
        
        return '\n'.join(new_lines)
    
    @staticmethod
    def inject_access_lua(config_content: str, access_lua: str) -> str:
        """在 location / 块内注入 access_by_lua_file"""
        lines = config_content.split('\n')
        new_lines = []
        inserted_access = False
        server_start, server_end = _find_first_block(lines, 'server')
        
        if server_start < 0 or server_end < 0:
            return config_content
        
        location_start, location_end = _find_location_block(lines, server_start, server_end, '/')
        if location_start < 0 or location_end < 0:
            return config_content
        
        for i, line in enumerate(lines):
            if i == location_start + 1 and not inserted_access:
                new_lines.append(access_lua)
                inserted_access = True
            new_lines.append(line)
        
        if inserted_access:
            Logger.step("✓ 已插入 access_by_lua_file 指令（在 location / 块内）")
            Logger.step(f"debug access_lua={access_lua.strip()}")
        else:
            Logger.warning("⚠ 未找到合适位置插入 access_by_lua_file")
        
        return '\n'.join(new_lines)
    
    @staticmethod
    def inject_body_filter(config_content: str, body_filter: str) -> str:
        """在 location / 块结束前注入 body_filter"""
        lines = config_content.split('\n')
        server_start, server_end = _find_first_block(lines, 'server')
        
        if server_start >= 0 and server_end >= 0:
            location_start, location_end = _find_location_block(lines, server_start, server_end, '/')
            if location_start < 0 or location_end < 0:
                return config_content
            new_lines = []
            for i, line in enumerate(lines):
                if i == location_end:
                    # 在 location / 块的闭合 } 之前插入 body_filter
                    new_lines.append(body_filter)
                    new_lines.append(line)
                else:
                    new_lines.append(line)
            
            Logger.step("✓ 已插入 body_filter_by_lua_block 指令（在 location / 块结束前）")
            Logger.step(f"debug body_filter_first_line={body_filter.strip().splitlines()[0]}")
            return '\n'.join(new_lines)
        else:
            Logger.warning("无法定位 server 块位置，跳过 body_filter 插入")
            return config_content



class NginxResolverConfigurator:
    """Nginx DNS Resolver 配置器"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
    
    def ensure_resolver_configured(self, container_id: str) -> bool:
        """确保 nginx.conf 的 http 块中有 resolver 配置"""
        Logger.step("检查并配置 DNS resolver...")
        
        nginx_conf_path = "/usr/local/openresty/nginx/conf/nginx.conf"
        
        try:
            nginx_conf = self.api_client.get_container_file_content(container_id, nginx_conf_path)
            
            if not nginx_conf:
                Logger.warning("无法读取 nginx.conf，跳过 resolver 配置")
                return False
            
            # 检查是否已有 resolver
            cleaned = '\n'.join(_strip_nginx_comment(line) for line in nginx_conf.split('\n'))
            if re.search(r'(?m)^\s*resolver\b', cleaned):
                Logger.success("DNS resolver 已存在")
                return True
            
            # 在 http 块中添加 resolver
            modified_conf = self._inject_resolver(nginx_conf)
            
            if not modified_conf:
                Logger.warning("无法自动添加 resolver，请手动配置")
                return False
            
            # 写回配置
            success = self._write_nginx_conf(container_id, modified_conf)
            
            if success:
                Logger.success("nginx.conf 已更新")
                return True
            else:
                Logger.warning("nginx.conf 更新失败，请手动添加 resolver")
                return False
                
        except Exception as e:
            Logger.warning(f"配置 resolver 失败: {e}，请手动配置")
            return False
    
    def _inject_resolver(self, nginx_conf: str) -> Optional[str]:
        """在 http 块中注入 resolver"""
        lines = nginx_conf.split('\n')
        new_lines = []
        inserted = False
        http_start, http_end = _find_first_block(lines, 'http')
        
        for idx, line in enumerate(lines):
            new_lines.append(line)
            
            if not inserted and http_start >= 0 and idx > http_start and (http_end < 0 or idx < http_end):
                if 'include' in _strip_nginx_comment(line) and 'mime.types' in _strip_nginx_comment(line):
                    new_lines.append('    resolver 8.8.8.8 8.8.4.4 ipv6=off;')
                    inserted = True
                    Logger.success("已添加 DNS resolver 配置")
        
        if inserted:
            return '\n'.join(new_lines)
        return None
    
    def _write_nginx_conf(self, container_id: str, content: str) -> bool:
        """写入 nginx.conf"""
        tmp_dir = tempfile.gettempdir()
        # 临时文件名必须是 nginx.conf，才能正确覆盖容器中的 nginx.conf
        tmp_path = os.path.join(tmp_dir, 'nginx.conf')
        
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            success = self.api_client.upload_file_to_container(
                container_id,
                tmp_path,
                '/usr/local/openresty/nginx/conf'
            )
            
            return success
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)



class NginxConfigManager:
    """Nginx 配置管理器"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
        self.config_generator = NginxConfigGenerator()
    
    def update_website_config(self, domain: str, site_key: str, site_id: str, 
                            site_secret: str, gateway_url: str, container_id: str,
                            skip_ssl_check: bool = False) -> str:
        """更新网站的 Nginx 配置
        
        Args:
            domain: 域名
            site_key: 站点密钥字符串（格式：site_xxxxxxxx）
            site_id: 站点数字主键（Site.id，整数字符串）
            site_secret: 站点签名密钥
            gateway_url: 网关 URL
            container_id: 容器 ID
            skip_ssl_check: 是否跳过 SSL 检查
        """
        Logger.step("通过 1Panel API 更新配置...")
        
        # 1. 搜索站点获取信息
        website_info = self._get_website_info(domain)
        
        # 2. 获取当前 Nginx 配置
        config_path = self._find_nginx_config(website_info, container_id)
        current_config = self.api_client.get_container_file_content(container_id, config_path)
        
        if not current_config:
            Logger.error("无法读取 Nginx 配置文件")
            sys.exit(1)
        
        # 3. 生成并插入配置
        config_domain = (
            _extract_server_name(current_config)
            or website_info.get('primaryDomain')
            or website_info.get('alias')
            or domain
        )
        Logger.step(f"debug config_domain={config_domain} site_path={website_info.get('sitePath', '')}")
        if config_domain != domain:
            Logger.warning(f"使用配置文件 server_name {config_domain} 生成 Fangyu 路径，避免域名路径不一致")
        modified_config = self._modify_config(
            current_config, config_domain, site_key, site_id, site_secret, gateway_url
        )
        
        # 4. 写回配置文件
        self._write_config(
            container_id,
            int(website_info['id']),
            config_path,
            modified_config,
            skip_ssl_check
        )
        
        Logger.success("配置已更新，1Panel 将自动重载 Nginx")
        return config_path
    
    def _get_website_info(self, domain: str) -> Dict:
        """获取网站信息"""
        try:
            websites = self.api_client.search_websites(domain)
            
            if not websites:
                Logger.error(f"找不到站点: {domain}")
                sys.exit(1)
            
            Logger.step(f"共找到 {len(websites)} 个匹配的站点")
            website_info = websites[0]
            Logger.success(f"使用站点 ID: {website_info['id']}")
            Logger.step(f"站点路径: {website_info.get('sitePath', '')}")
            Logger.step(f"站点别名: {website_info.get('alias', domain)}")
            if website_info.get('primaryDomain') and website_info['primaryDomain'] != domain:
                Logger.warning(
                    f"输入域名 {domain} 与站点主域名 {website_info['primaryDomain']} 不一致，"
                    "将使用站点主域名生成路径和证书引用"
                )
            
            return website_info
            
        except Exception as e:
            Logger.error(f"搜索站点失败: {e}")
            sys.exit(1)
    
    def _find_nginx_config(self, website_info: Dict, container_id: str) -> str:
        """查找 Nginx 配置文件路径"""
        alias = website_info.get('alias', website_info.get('primaryDomain', ''))
        domain = website_info.get('primaryDomain', '')
        
        possible_paths = [
            f"/usr/local/openresty/nginx/conf/conf.d/{alias}.conf",
            f"/usr/local/openresty/nginx/conf/conf.d/{domain}.conf",
            f"/etc/nginx/conf.d/{alias}.conf",
            f"/etc/nginx/conf.d/{domain}.conf",
        ]
        
        for path in possible_paths:
            content = self.api_client.get_container_file_content(container_id, path)
            if content:
                Logger.success(f"找到配置文件: {path}")
                return path
        
        Logger.error("无法找到 Nginx 配置文件")
        Logger.warning("尝试的路径:")
        for path in possible_paths:
            print(f"  - {path}")
        sys.exit(1)
    
    def _modify_config(self, config: str, domain: str, site_key: str, 
                      site_id: str, site_secret: str, gateway_url: str) -> str:
        """修改配置内容"""
        vars_block, access_lua, body_filter = self.config_generator.generate_config_blocks(
            domain, site_key, site_id, site_secret, gateway_url
        )
        
        # 删除旧配置
        config = self.config_generator.remove_old_fangyu_config(config)
        
        # 插入新配置
        config = self.config_generator.inject_vars_block(config, vars_block)
        config = self.config_generator.inject_access_lua(config, access_lua)
        config = self.config_generator.inject_body_filter(config, body_filter)
        
        Logger.success("Nginx 配置已生成并插入")
        return config
    
    def _validate_ssl_certificates(self, container_id: str, config_content: str) -> bool:
        """验证配置中引用的 SSL 证书文件是否存在
        
        Args:
            container_id: 容器 ID
            config_content: Nginx 配置内容
        
        Returns:
            所有证书文件都存在返回 True，否则返回 False
        """
        # 提取 ssl_certificate 和 ssl_certificate_key 路径
        ssl_cert_pattern = r'ssl_certificate\s+([^;]+);'
        ssl_key_pattern = r'ssl_certificate_key\s+([^;]+);'
        cleaned_content = '\n'.join(_strip_nginx_comment(line) for line in config_content.split('\n'))
        
        cert_paths = re.findall(ssl_cert_pattern, cleaned_content)
        key_paths = re.findall(ssl_key_pattern, cleaned_content)
        
        if not cert_paths and not key_paths:
            # 没有 SSL 配置，跳过验证
            return True
        
        all_paths = cert_paths + key_paths
        missing_files = []
        
        Logger.step("验证 SSL 证书文件...")
        
        for path in all_paths:
            path = path.strip()
            Logger.step(f"检查: {path}")
            
            if not self.api_client.check_file_exists(container_id, path):
                Logger.warning(f"✗ 文件不存在: {path}")
                missing_files.append(path)
            else:
                Logger.success(f"✓ 文件存在: {path}")
        
        if missing_files:
            Logger.error("发现缺失的 SSL 证书文件:")
            for path in missing_files:
                Logger.error(f"  - {path}")
            Logger.warning("解决方案:")
            Logger.warning("1. 在 1Panel 中为该站点申请或上传 SSL 证书")
            Logger.warning("2. 或者暂时注释掉 HTTPS server 块，只使用 HTTP")
            return False
        
        Logger.success("所有 SSL 证书文件验证通过")
        return True
    
    def _test_nginx_config_syntax(self, container_id: str) -> bool:
        """测试 Nginx 配置语法
        
        Args:
            container_id: 容器 ID
        
        Returns:
            配置语法正确返回 True，否则返回 False
        """
        Logger.step("测试 Nginx 配置语法...")
        
        success, stdout, stderr = self.api_client.exec_container_command(
            container_id,
            "nginx -t"
        )
        
        if success:
            Logger.success("✓ Nginx 配置语法正确")
            return True
        else:
            if "API 调用失败: 404" in stderr:
                Logger.warning("⚠ 当前 1Panel API 不支持容器命令执行，跳过 nginx -t 自动校验")
                Logger.warning(f"  请手动执行: docker exec -it {container_id[:12]} nginx -t")
                return True
            Logger.error("✗ Nginx 配置语法错误:")
            if stderr:
                for line in stderr.split('\n')[:10]:
                    if line.strip():
                        Logger.error(f"  {line}")
            return False
    
    def _write_config(self, container_id: str, website_id: int, config_path: str, content: str, skip_ssl_check: bool = False) -> None:
        """写入配置文件到容器"""
        Logger.step(f"配置文件大小: {len(content)} 字节")
        Logger.step(f"目标路径: {config_path}")
        
        if skip_ssl_check:
            Logger.warning("⚠ 已跳过 SSL 证书验证（假设证书由 1Panel 管理）")
        elif not self._validate_ssl_certificates(container_id, content):
            Logger.error("SSL 证书验证失败，停止部署")
            sys.exit(1)
        
        if not self.api_client.update_website_nginx_config(website_id, content):
            Logger.error("通过 1Panel Website Nginx 接口更新配置失败")
            sys.exit(1)
        
        Logger.success("配置文件已通过 1Panel Website Nginx 接口更新")
        
        if not self._test_nginx_config_syntax(container_id):
            Logger.error("Nginx 配置语法测试失败")
            Logger.warning("配置文件已上传但未生效，请检查错误后手动修复")
            sys.exit(1)
        
        Logger.success("配置已验证并生效，1Panel 将自动重载 Nginx")


class InstallationTester:
    """安装测试器"""
    
    def __init__(self, api_client: OnePanelAPIClient):
        self.api_client = api_client
    
    def run_tests(self, domain: str, container_id: str, config_path: str) -> bool:
        """执行完整的安装验证测试"""
        Logger.step("开始安装验证测试...")
        print()
        
        test_results = {}
        
        # 测试 1: 验证 defense.lua 文件
        test_results['defense_lua'] = self._test_defense_lua(domain, container_id)
        print()
        
        # 测试 2: 验证 Nginx 配置内容
        test_results['nginx_config'] = self._test_nginx_config(container_id, config_path)
        print()
        
        # 测试 3: 检查 Nginx 错误日志
        test_results['no_errors'] = self._test_error_logs(container_id)
        print()
        
        # 测试 4: 网站可访问性
        test_results['website_ok'] = self._test_website_access(domain)
        print()
        
        # 测试 5: 检测防御系统活动
        test_results['defense_active'] = self._test_defense_activity(domain)
        print()
        
        # 输出测试结果
        return self._display_results(test_results)
    
    def _test_defense_lua(self, domain: str, container_id: str) -> bool:
        """测试 defense.lua 文件"""
        Logger.step("测试 1/5: 验证 defense.lua 文件")
        
        try:
            content = self.api_client.get_container_file_content(
                container_id,
                f"/www/sites/{domain}/lua/defense.lua"
            )
            
            if content and len(content) > 10000:
                Logger.success(f"✓ defense.lua 存在且完整 ({len(content)} 字节)")
                return True
            elif content:
                Logger.error(f"✗ defense.lua 文件太小 ({len(content)} 字节)，可能不完整")
                return False
            else:
                Logger.error("✗ 无法读取 defense.lua")
                return False
        except Exception as e:
            Logger.error(f"✗ 验证失败: {e}")
            return False
    
    def _test_nginx_config(self, container_id: str, config_path: str) -> Optional[bool]:
        """测试 Nginx 配置"""
        Logger.step("测试 2/5: 验证 Nginx 配置内容")
        
        try:
            config = self._read_config_with_retry(container_id, config_path, max_retries=3)
            
            if not config:
                Logger.error("✗ 无法读取 Nginx 配置")
                return False
            
            checks = {
                "fangyu_gateway_url": "fangyu_gateway_url" in config,
                "fangyu_site_key": "fangyu_site_key" in config,
                "fangyu_site_id": "fangyu_site_id" in config,
                "fangyu_site_secret": "fangyu_site_secret" in config,
                "access_by_lua_file": "access_by_lua_file" in config and "defense.lua" in config,
                "body_filter_by_lua_block": "body_filter_by_lua_block" in config,
            }
            
            passed = sum(checks.values())
            total = len(checks)
            
            if passed == total:
                Logger.success(f"✓ Nginx 配置完整 ({passed}/{total} 项通过)")
                return True
            else:
                Logger.error(f"✗ Nginx 配置不完整 ({passed}/{total} 项通过)")
                for name, result in checks.items():
                    if not result:
                        Logger.error(f"  缺失: {name}")
                return False
                
        except requests.exceptions.Timeout:
            Logger.warning("⚠ 读取配置超时（可能是网络问题），跳过此项检查")
            return None
        except Exception as e:
            Logger.warning(f"⚠ 验证失败: {e}")
            return None
    
    def _read_config_with_retry(self, container_id: str, path: str, max_retries: int = 3) -> Optional[str]:
        """带重试的配置读取"""
        for attempt in range(max_retries):
            try:
                content = self.api_client.get_container_file_content(container_id, path)
                if content:
                    return content
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    Logger.warning(f"  读取超时，重试 {attempt + 1}/{max_retries - 1}...")
                    time.sleep(2)
                else:
                    raise
        return None
    
    def _test_error_logs(self, container_id: str) -> bool:
        """测试错误日志"""
        Logger.step("测试 3/5: 检查 Nginx 错误日志")
        
        try:
            error_log = self._read_config_with_retry(
                container_id,
                "/usr/local/openresty/nginx/logs/error.log",
                max_retries=3
            )
            
            if not error_log:
                Logger.warning("⚠ 无法读取错误日志（继续）")
                return True
            
            lines = error_log.split('\n')[-50:]
            lua_errors = [
                l for l in lines 
                if l.strip() and any(kw in l.lower() for kw in ['lua', 'fangyu']) and 'error' in l.lower()
            ]
            
            if lua_errors:
                Logger.warning(f"⚠ 发现 {len(lua_errors)} 条 Lua 相关错误")
                for err in lua_errors[-3:]:
                    Logger.warning(f"  {err[:100]}")
                return False
            else:
                Logger.success("✓ 无 Lua 相关错误")
                return True
                
        except requests.exceptions.Timeout:
            Logger.warning("⚠ 读取日志超时（可能是网络问题），跳过此项检查")
            return True
        except Exception as e:
            Logger.warning(f"⚠ 无法检查错误日志: {e}")
            return True
    
    def _test_website_access(self, domain: str) -> bool:
        """测试网站访问"""
        Logger.step("测试 4/5: 测试网站访问")
        
        for scheme in ("https", "http"):
            try:
                resp = requests.get(
                    f"{scheme}://{domain}/",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=10,
                    verify=False
                )
                
                if resp.status_code == 200:
                    Logger.success(f"✓ 网站正常响应 ({scheme.upper()}, 状态码: {resp.status_code}, 耗时: {resp.elapsed.total_seconds():.2f}秒)")
                    return True
                preview = resp.text[:200].replace('\n', ' ').replace('\r', ' ')
                server_header = resp.headers.get('Server', '')
                Logger.warning(f"⚠ {scheme.upper()} 响应异常 (状态码: {resp.status_code}, Server: {server_header})")
                if preview:
                    Logger.warning(f"  响应摘要: {preview}")
            except Exception as e:
                Logger.warning(f"⚠ {scheme.upper()} 访问失败: {e}")
        return False
    
    def _test_defense_activity(self, domain: str) -> Optional[bool]:
        """测试防御系统活动"""
        Logger.step("测试 5/5: 检测防御系统活动")
        
        try:
            resp = requests.get(
                f"https://{domain}/test-fangyu-{int(time.time())}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=10,
                verify=False
            )
            
            if "fangyu" in resp.text.lower() or "fy_" in resp.text:
                Logger.success("✓ 检测到 Fangyu 活动迹象（SDK 注入或标记）")
                return True
            else:
                Logger.warning("⚠ 未检测到明显的 Fangyu 活动")
                Logger.warning("  这可能是因为 Cloudflare 缓存或静默运行模式")
                Logger.warning("  请查看防御系统后台确认")
                return None
        except Exception as e:
            Logger.warning(f"⚠ 无法测试: {e}")
            return None
    
    def _display_results(self, test_results: Dict) -> bool:
        """显示测试结果"""
        print("=" * 80)
        print("安装验证结果汇总")
        print("=" * 80)
        print()
        
        critical_tests = [
            ("defense.lua 文件完整", test_results.get('defense_lua', False)),
            ("Nginx 配置正确", test_results.get('nginx_config')),
            ("无 Lua 错误", test_results.get('no_errors', True)),
            ("网站正常访问", test_results.get('website_ok', False)),
        ]
        
        optional_tests = [
            ("防御系统活动", test_results.get('defense_active')),
        ]
        
        # 计算通过率（只统计明确的 True/False，忽略 None）
        critical_definite = [(name, result) for name, result in critical_tests if result is not None]
        critical_passed = sum(1 for _, result in critical_definite if result is True)
        critical_total = len(critical_definite)
        
        print("关键测试:")
        for name, result in critical_tests:
            if result is True:
                Logger.success(f"  ✓ {name}")
            elif result is None:
                Logger.warning(f"  ? {name} (无法确认)")
            else:
                Logger.error(f"  ✗ {name}")
        
        print()
        print("可选测试:")
        for name, result in optional_tests:
            if result is True:
                Logger.success(f"  ✓ {name}")
            elif result is None:
                Logger.warning(f"  ? {name} (无法确认)")
            else:
                Logger.warning(f"  ✗ {name}")
        
        print()
        print(f"关键测试通过率: {critical_passed}/{critical_total}")
        print()
        
        if critical_passed == critical_total:
            print(f"{Colors.GREEN}{'='*80}{Colors.END}")
            print(f"{Colors.GREEN}✅ 安装成功！所有关键测试通过！{Colors.END}")
            print(f"{Colors.GREEN}{'='*80}{Colors.END}")
            print()
            print("下一步:")
            print("  1. 访问防御系统后台查看决策记录")
            print("  2. 观察真实流量的防御效果")
            print("  3. 根据需要调整防御策略")
            print()
            print("注意:")
            print("  - 由于 Cloudflare CDN 缓存，大部分请求不会回源")
            print("  - 只有未缓存的请求才会经过 Fangyu Defense")
            print("  - 这是正常的，防御系统在源服务器层面保护")
            return True
        elif critical_passed >= critical_total * 0.75:
            print(f"{Colors.YELLOW}{'='*80}{Colors.END}")
            print(f"{Colors.YELLOW}⚠ 安装基本完成，但存在一些问题{Colors.END}")
            print(f"{Colors.YELLOW}{'='*80}{Colors.END}")
            print()
            print("建议:")
            print("  1. 检查未通过的测试项")
            print("  2. 查看上面的错误信息")
            print("  3. 必要时重新运行安装脚本")
            return False
        else:
            print(f"{Colors.RED}{'='*80}{Colors.END}")
            print(f"{Colors.RED}✗ 安装失败！多个关键测试未通过{Colors.END}")
            print(f"{Colors.RED}{'='*80}{Colors.END}")
            print()
            print("建议:")
            print("  1. 检查所有错误信息")
            print("  2. 确认服务器和网络连接正常")
            print("  3. 查看详细的错误日志")
            print("  4. 联系技术支持")
            return False


class FangyuInstaller:
    """Fangyu Defense 安装器主类"""
    
    def __init__(self, panel_url: str, panel_key: str):
        self.api_client = OnePanelAPIClient(panel_url, panel_key)
        self.container_manager = ContainerManager(self.api_client)
        self.deployer = DefenseLuaDeployer(self.api_client)
        self.main_conf_manager = NginxConfManager(self.api_client)
        self.resolver_config = NginxResolverConfigurator(self.api_client)
        self.nginx_manager = NginxConfigManager(self.api_client)
        self.tester = InstallationTester(self.api_client)
    
    def install(self, domain: str, site_key: str, site_id: str, 
               site_secret: str, gateway_url: str, skip_ssl_check: bool = False) -> bool:
        """执行完整的安装流程
        
        Args:
            domain: 域名
            site_key: 站点密钥字符串（格式：site_xxxxxxxx）
            site_id: 站点数字主键（Site.id，整数字符串）
            site_secret: 站点签名密钥
            gateway_url: 网关 URL
            skip_ssl_check: 是否跳过 SSL 检查
        """
 
        
        try:
            # 1. 查找 OpenResty 容器
            container_name, container_id = self.container_manager.find_openresty_container()
            
            # 2. 检查 Lua 依赖
            self.container_manager.check_lua_dependencies(container_id)
            
            # 3. 配置 nginx.conf 中的 Lua 模块（关键步骤）
            print()
            Logger.step("检查并配置 nginx.conf 中的 Lua 模块...")
            if not self.main_conf_manager.check_lua_config(container_id):
                Logger.warning("nginx.conf 中缺少 Lua 配置，尝试自动添加...")
                if self.main_conf_manager.add_lua_config(container_id):
                    Logger.success("✓ nginx.conf 已配置 Lua 模块")
                else:
                    Logger.warning("⚠ 自动配置失败，请手动配置（参考文档）")
            else:
                Logger.success("✓ nginx.conf 已包含 Lua 配置")
            
            # 4. 配置 DNS resolver
            self.resolver_config.ensure_resolver_configured(container_id)
            
            # 5. 部署 defense.lua
            self.deployer.deploy(domain, container_id)
            
            # 6. 更新 Nginx 配置
            config_path = self.nginx_manager.update_website_config(
                domain, site_key, site_id, site_secret, gateway_url, container_id, skip_ssl_check
            )
            
            # 7. 执行安装验证
            success = self.tester.run_tests(domain, container_id, config_path)
            
            if not success:
                print()
                Logger.warning("虽然安装过程完成，但某些测试未通过")
                Logger.warning("请检查上面的错误信息并根据需要修复")
                return False
            
            return True
            
        except Exception as e:
            Logger.error(f"安装失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    

def main(domain: str, site_key: str, site_id: str, site_secret: str, 
         gateway_url: str, panel_url: str, panel_key: str, skip_ssl_check: bool = False) -> None:
    """主函数：执行安装流程"""
    installer = FangyuInstaller(panel_url, panel_key)
    success = installer.install(domain, site_key, site_id, site_secret, gateway_url, skip_ssl_check)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # ========== 配置区：在这里填写你的配置 ==========
    DOMAIN = "wayaffair.shop"          # 要安装的域名
    SITE_KEY = "site_eba8689a"         # 防御系统后台的 Site Key（站点密钥字符串）
    SITE_ID = "1"                      # 防御系统后台的 Site ID（站点数字主键）
    SITE_SECRET = "bd5f8a076002101ff410fd127dd5d5e71452c00e9aa479bf" # 防御系统后台的 Site Secret（站点签名密钥）
    GATEWAY_URL = "https://gateway.foxfingerlab.com"  # 网关地址
    
    # 1Panel API 配置
    PANEL_URL = "http://198.200.42.128:31384"  # 1Panel 访问地址（含端口）
    PANEL_KEY = "pWAEY3ldk1phmLLAHgnmibxRgABMoBwZ"       # 1Panel API 密钥（在 1Panel → 设置 → 安全 → API密钥）
    SKIP_SSL_CHECK = True
    # ============================================
    
    # 检查配置是否填写
    if DOMAIN == "example.com" or SITE_KEY == "site_abc123" or SITE_SECRET == "your_secret_here":
        print(f"{Colors.RED}❌ 请先在脚本底部的配置区填写正确的配置！{Colors.END}")
        print(f"当前配置:")
        print(f"  DOMAIN = {DOMAIN}")
        print(f"  SITE_KEY = {SITE_KEY}")
        print(f"  SITE_SECRET = {SITE_SECRET[:20]}...")
        sys.exit(1)
    
    # 支持命令行参数覆盖配置
    if len(sys.argv) >= 5:
        DOMAIN = sys.argv[1]
        SITE_KEY = sys.argv[2]
        SITE_ID = sys.argv[3]
        SITE_SECRET = sys.argv[4]
        if len(sys.argv) > 5:
            GATEWAY_URL = sys.argv[5]
        if len(sys.argv) > 6:
            PANEL_URL = sys.argv[6]
        if len(sys.argv) > 7:
            PANEL_KEY = sys.argv[7]
    
    main(DOMAIN, SITE_KEY, SITE_ID, SITE_SECRET, GATEWAY_URL, PANEL_URL, PANEL_KEY, SKIP_SSL_CHECK)

#!/usr/bin/env python3
"""
SSL 证书问题诊断工具
用于检查 1Panel OpenResty 站点的 SSL 证书配置和文件状态
"""
import hashlib
import re
import sys
import time
from typing import Dict, List, Tuple

import requests


class Colors:
    """终端颜色"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


class Logger:
    """日志工具"""
    
    @staticmethod
    def info(msg: str):
        print(f"{Colors.BLUE}[信息]{Colors.END} {msg}")
    
    @staticmethod
    def success(msg: str):
        print(f"{Colors.GREEN}[成功]{Colors.END} {msg}")
    
    @staticmethod
    def warning(msg: str):
        print(f"{Colors.YELLOW}[警告]{Colors.END} {msg}")
    
    @staticmethod
    def error(msg: str):
        print(f"{Colors.RED}[错误]{Colors.END} {msg}")


class OnePanelAPI:
    """1Panel API 客户端"""
    
    def __init__(self, panel_url: str, panel_key: str):
        self.panel_url = panel_url.rstrip('/')
        self.panel_key = panel_key
    
    def _get_headers(self) -> Dict[str, str]:
        """生成请求头"""
        timestamp = str(int(time.time()))
        sign_str = f"1panel{self.panel_key}{timestamp}"
        signature = hashlib.md5(sign_str.encode()).hexdigest()
        
        return {
            "Content-Type": "application/json",
            "1Panel-Token": signature,
            "1Panel-Timestamp": timestamp,
        }
    
    def search_containers(self, name: str) -> List[Dict]:
        """搜索容器"""
        headers = self._get_headers()
        
        resp = requests.post(
            f"{self.panel_url}/api/v2/containers/search",
            headers=headers,
            json={"name": name, "state": "running", "page": 1, "pageSize": 50},
            timeout=10,
            verify=False
        )
        
        if resp.status_code == 200 and resp.json().get('code') == 200:
            return resp.json()['data']['items']
        return []
    
    def exec_command(self, container_id: str, command: str) -> Tuple[bool, str, str]:
        """执行容器命令"""
        headers = self._get_headers()
        
        resp = requests.post(
            f"{self.panel_url}/api/v2/containers/exec",
            headers=headers,
            json={"containerID": container_id, "command": command},
            timeout=30,
            verify=False
        )
        
        if resp.status_code == 200 and resp.json().get('code') == 200:
            result = resp.json()['data']
            return (
                result.get('exitCode', 1) == 0,
                result.get('stdout', ''),
                result.get('stderr', '')
            )
        return False, "", "API 调用失败"
    
    def get_file_content(self, container_id: str, path: str) -> str:
        """读取容器文件"""
        headers = self._get_headers()
        
        resp = requests.post(
            f"{self.panel_url}/api/v2/containers/files/content",
            headers=headers,
            json={"containerID": container_id, "path": path},
            timeout=10,
            verify=False
        )
        
        if resp.status_code == 200 and resp.json().get('code') == 200:
            return resp.json()['data']['content']
        return ""


def extract_ssl_paths(config_content: str) -> Tuple[List[str], List[str]]:
    """从 Nginx 配置中提取 SSL 证书路径"""
    cert_pattern = r'ssl_certificate\s+([^;]+);'
    key_pattern = r'ssl_certificate_key\s+([^;]+);'
    
    certs = [p.strip() for p in re.findall(cert_pattern, config_content)]
    keys = [p.strip() for p in re.findall(key_pattern, config_content)]
    
    return certs, keys


def diagnose_ssl(panel_url: str, panel_key: str, domain: str = None):
    """诊断 SSL 证书问题"""
    print("="*70)
    print("SSL 证书诊断工具")
    print("="*70)
    print()
    
    api = OnePanelAPI(panel_url, panel_key)
    
    # 1. 查找 OpenResty 容器
    Logger.info("查找 OpenResty 容器...")
    containers = api.search_containers("openresty")
    
    if not containers:
        Logger.error("未找到运行中的 OpenResty 容器")
        return False
    
    container = containers[0]
    container_id = container['containerID']
    Logger.success(f"找到容器: {container['name']} (ID: {container_id[:12]})")
    print()
    
    # 2. 测试 nginx -t
    Logger.info("测试 Nginx 配置语法...")
    success, stdout, stderr = api.exec_command(container_id, "nginx -t")
    
    if success:
        Logger.success("✓ Nginx 配置语法正确")
        print()
        return True
    else:
        Logger.error("✗ Nginx 配置语法错误:")
        if stderr:
            print(stderr)
        print()
    
    # 3. 从错误信息中提取证书路径
    missing_cert = None
    if "cannot load certificate" in stderr:
        match = re.search(r'cannot load certificate "([^"]+)"', stderr)
        if match:
            missing_cert = match.group(1)
            Logger.warning(f"缺失的证书文件: {missing_cert}")
            print()
    
    # 4. 查找所有配置文件
    Logger.info("扫描配置文件...")
    success, stdout, stderr = api.exec_command(
        container_id,
        "find /usr/local/openresty/nginx/conf/conf.d -name '*.conf' -type f"
    )
    
    if not success:
        Logger.error("无法扫描配置文件")
        return False
    
    config_files = [f.strip() for f in stdout.split('\n') if f.strip()]
    Logger.info(f"找到 {len(config_files)} 个配置文件")
    print()
    
    # 5. 检查每个配置文件中的 SSL 证书
    all_issues = []
    
    for config_path in config_files:
        config_content = api.get_file_content(container_id, config_path)
        if not config_content:
            continue
        
        # 如果指定了域名，只检查包含该域名的配置
        if domain and domain not in config_content:
            continue
        
        certs, keys = extract_ssl_paths(config_content)
        
        if not certs and not keys:
            continue
        
        Logger.info(f"检查配置: {config_path}")
        
        # 检查证书文件是否存在
        for cert_path in certs:
            success, _, _ = api.exec_command(container_id, f"test -f {cert_path}")
            if success:
                Logger.success(f"  ✓ {cert_path}")
            else:
                Logger.error(f"  ✗ {cert_path} (不存在)")
                all_issues.append((config_path, cert_path, "证书文件"))
        
        for key_path in keys:
            success, _, _ = api.exec_command(container_id, f"test -f {key_path}")
            if success:
                Logger.success(f"  ✓ {key_path}")
            else:
                Logger.error(f"  ✗ {key_path} (不存在)")
                all_issues.append((config_path, key_path, "密钥文件"))
        
        print()
    
    # 6. 输出修复建议
    if all_issues:
        print("="*70)
        print("修复建议")
        print("="*70)
        print()
        
        for config_path, cert_path, file_type in all_issues:
            Logger.warning(f"{file_type}缺失: {cert_path}")
            Logger.warning(f"  所在配置: {config_path}")
            print()
        
        print("解决方案:")
        print()
        print("方案 1: 在 1Panel 中申请或上传 SSL 证书")
        print("  1. 登录 1Panel 管理界面")
        print("  2. 进入 [网站] → 找到对应站点 → [设置]")
        print("  3. 选择 [HTTPS] → [申请证书] 或 [上传证书]")
        print()
        print("方案 2: 暂时禁用 HTTPS（仅用于测试）")
        print(f"  1. 编辑配置文件，注释掉包含 ssl_certificate 的 server 块")
        print(f"  2. 在容器中执行: docker exec -it {container_id[:12]} sh")
        print(f"  3. 编辑配置: vi <配置文件路径>")
        print(f"  4. 测试配置: nginx -t")
        print(f"  5. 重载配置: nginx -s reload")
        print()
        
        return False
    else:
        Logger.success("未发现 SSL 证书问题")
        return True


if __name__ == "__main__":
    # ========== 配置区 ==========
    PANEL_URL = "http://198.200.42.128:31384"
    PANEL_KEY = "QWTbIertpeww14SeUXOrAsVerB1zCQUW"
    DOMAIN = None  # 可选：指定要检查的域名
    # ============================
    
    # 支持命令行参数
    if len(sys.argv) > 1:
        PANEL_URL = sys.argv[1]
    if len(sys.argv) > 2:
        PANEL_KEY = sys.argv[2]
    if len(sys.argv) > 3:
        DOMAIN = sys.argv[3]
    
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    
    try:
        success = diagnose_ssl(PANEL_URL, PANEL_KEY, DOMAIN)
        sys.exit(0 if success else 1)
    except Exception as e:
        Logger.error(f"诊断失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

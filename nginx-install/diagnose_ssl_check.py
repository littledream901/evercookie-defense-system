#!/usr/bin/env python3
"""
诊断 SSL 证书文件检查问题
"""
import hashlib
import time
import requests
import warnings
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 配置
PANEL_URL = "http://198.200.42.128:31384"
PANEL_KEY = "pWAEY3ldk1phmLLAHgnmibxRgABMoBwZ"
CONTAINER_ID = "a5444effbb06"  # 从之前的日志中获取

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

def generate_signature():
    timestamp = str(int(time.time()))
    sign_str = f"1panel{PANEL_KEY}{timestamp}"
    signature = hashlib.md5(sign_str.encode()).hexdigest()
    return signature, timestamp

def get_headers():
    signature, timestamp = generate_signature()
    return {
        "Content-Type": "application/json",
        "1Panel-Token": signature,
        "1Panel-Timestamp": timestamp,
    }

def exec_command(container_id, command):
    """执行容器命令"""
    headers = get_headers()
    
    print(f"执行命令: {command}")
    
    resp = requests.post(
        f"{PANEL_URL}/api/v2/containers/exec",
        headers=headers,
        json={
            "containerID": container_id,
            "command": command
        },
        timeout=10,
        verify=False
    )
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get('code') == 200:
            result = data.get('data', {})
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            exitCode = result.get('exitCode', -1)
            
            print(f"  退出码: {exitCode}")
            print(f"  标准输出: {stdout}")
            if stderr:
                print(f"  错误输出: {stderr}")
            
            return exitCode == 0, stdout, stderr
        else:
            print(f"  API 错误: {data}")
            return False, "", f"API error: {data.get('message', '')}"
    else:
        print(f"  HTTP 错误: {resp.status_code}")
        return False, "", f"HTTP error: {resp.status_code}"

def check_file(container_id, path):
    """检查文件是否存在"""
    print(f"\n检查文件: {path}")
    
    # 方法 1: test -f
    success, stdout, stderr = exec_command(
        container_id,
        f"test -f {path} && echo 'exists' || echo 'not_found'"
    )
    print(f"  方法1 (test -f): {'存在' if success and 'exists' in stdout else '不存在'}")
    
    # 方法 2: ls
    success, stdout, stderr = exec_command(
        container_id,
        f"ls -lh {path}"
    )
    print(f"  方法2 (ls): {'存在' if success else '不存在'}")
    
    # 方法 3: stat
    success, stdout, stderr = exec_command(
        container_id,
        f"stat {path}"
    )
    print(f"  方法3 (stat): {'存在' if success else '不存在'}")

if __name__ == "__main__":
    print("=" * 80)
    print("SSL 证书文件诊断")
    print("=" * 80)
    
    # 检查不同路径
    paths = [
        "/www/sites/wayaffair.shop/ssl/fullchain.pem",
        "/www/sites/wayaffair.shop/ssl/privkey.pem",
        "/opt/1panel/www/sites/wayaffair.shop/ssl/fullchain.pem",
        "/opt/1panel/www/sites/wayaffair.shop/ssl/privkey.pem",
    ]
    
    for path in paths:
        check_file(CONTAINER_ID, path)
    
    print("\n" + "=" * 80)
    print("检查容器内的实际目录结构")
    print("=" * 80)
    
    # 检查目录结构
    exec_command(CONTAINER_ID, "ls -la /www/sites/wayaffair.shop/")
    exec_command(CONTAINER_ID, "ls -la /www/sites/wayaffair.shop/ssl/")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试 Cloudflare Worker 上传请求"""

import json
import requests
from requests_toolbelt import MultipartEncoder

# 配置
CF_API_TOKEN = "YOUR_CF_API_TOKEN"  # 替换为你的 Token
CF_ACCOUNT_ID = "YOUR_ACCOUNT_ID"  # 替换为你的 Account ID
WORKER_NAME = "test-worker"

# 读取脚本
script_path = r"e:\Python\evercookie-defense-system\Evercookie Defense System V2\adapters\shopify\cloudflare_worker\worker.js"
with open(script_path, 'r', encoding='utf-8') as f:
    script_content = f.read()

print(f"脚本大小: {len(script_content)} 字节")
print("\n尝试方法 1: 使用 requests files 参数...")

# 方法 1: 标准 files 参数
metadata = {'main_module': f'{WORKER_NAME}.js'}
files = {
    'metadata': (None, json.dumps(metadata), 'application/json'),
    f'{WORKER_NAME}.js': (f'{WORKER_NAME}.js', script_content, 'application/javascript')
}

headers = {'Authorization': f'Bearer {CF_API_TOKEN}'}
url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/workers/scripts/{WORKER_NAME}"

response = requests.put(url, headers=headers, files=files)
print(f"状态码: {response.status_code}")
print(f"响应: {response.text[:500]}")

if response.status_code != 200:
    print("\n尝试方法 2: 使用 MultipartEncoder...")
    
    # 方法 2: MultipartEncoder
    try:
        fields = {
            'metadata': ('metadata', json.dumps(metadata), 'application/json'),
            f'{WORKER_NAME}.js': (f'{WORKER_NAME}.js', script_content, 'application/javascript')
        }
        
        encoder = MultipartEncoder(fields=fields)
        headers2 = {
            'Authorization': f'Bearer {CF_API_TOKEN}',
            'Content-Type': encoder.content_type
        }
        
        response2 = requests.put(url, headers=headers2, data=encoder)
        print(f"状态码: {response2.status_code}")
        print(f"响应: {response2.text[:500]}")
    except ImportError:
        print("需要安装 requests-toolbelt: pip install requests-toolbelt")

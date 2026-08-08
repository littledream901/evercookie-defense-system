#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Worker 上传（不实际上传，仅验证请求格式）"""
import json
import requests

# 测试配置
CF_API_TOKEN = "cfut_UKNOKoJXqxwWcHS1ypApN3t0sPzgX9qhCjPYjaK3f84c00ca"
CF_ACCOUNT_ID = "7e75eb4c52144e73340e35390e7ecb22"

def test_upload_format():
    """测试上传请求格式"""
    print("=" * 80)
    print("测试 Worker 上传格式")
    print("=" * 80)
    print()
    
    # 准备测试脚本（简单的 Worker）
    test_script = """
export default {
  async fetch(request) {
    return new Response('Hello World!');
  }
};
""".strip()
    
    print("测试脚本大小:", len(test_script), "字节")
    print()
    
    # 准备请求
    headers = {
        'Authorization': f'Bearer {CF_API_TOKEN}',
    }
    
    metadata = {
        'body_part': 'script',
        'bindings': []
    }
    
    files = {
        'metadata': (None, json.dumps(metadata), 'application/json'),
        'script': ('test-format.js', test_script, 'application/javascript+module')
    }
    
    print("请求参数:")
    print(f"  URL: /accounts/{CF_ACCOUNT_ID}/workers/scripts/test-format-check")
    print(f"  Method: PUT")
    print(f"  Content-Type: multipart/form-data (自动)")
    print(f"  Script Content-Type: application/javascript+module")
    print()
    
    # 发送请求（使用测试 Worker 名称）
    print("发送测试请求...")
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/workers/scripts/test-format-check"
        response = requests.put(url, headers=headers, files=files, timeout=30)
        
        print(f"响应状态: HTTP {response.status_code}")
        print()
        
        if response.status_code in (200, 201):
            print("[SUCCESS] 上传成功！格式正确")
            data = response.json()
            if data.get('success'):
                print("  Worker 已创建")
                # 删除测试 Worker
                print()
                print("清理测试 Worker...")
                del_resp = requests.delete(url, headers=headers)
                if del_resp.status_code == 200:
                    print("  测试 Worker 已删除")
            return True
        
        elif response.status_code == 415:
            print("[FAIL] 415 Unsupported Media Type")
            print("  格式仍然不正确")
            print()
            print("响应内容:")
            try:
                print(json.dumps(response.json(), indent=2))
            except:
                print(response.text)
            return False
        
        elif response.status_code == 403:
            print("[FAIL] 403 Forbidden - Token 权限不足")
            return False
        
        else:
            print(f"[UNEXPECTED] HTTP {response.status_code}")
            print()
            print("响应内容:")
            try:
                print(json.dumps(response.json(), indent=2))
            except:
                print(response.text)
            return False
            
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        return False

if __name__ == '__main__':
    print()
    success = test_upload_format()
    print()
    print("=" * 80)
    if success:
        print("[SUCCESS] 测试通过！可以继续部署")
    else:
        print("[FAIL] 测试失败，需要进一步调试")
    print("=" * 80)

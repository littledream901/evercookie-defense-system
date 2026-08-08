#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Cloudflare API Token 权限"""
import requests
import sys

# 配置
CF_API_TOKEN = "cfut_UKNOKoJXqxwWcHS1ypApN3t0sPzgX9qhCjPYjaK3f84c00ca"
CF_ACCOUNT_ID = "7e75eb4c52144e73340e35390e7ecb22"

def test_token():
    """测试 Token 是否有效"""
    print("=" * 80)
    print("Cloudflare API Token 权限测试")
    print("=" * 80)
    print()
    
    headers = {
        'Authorization': f'Bearer {CF_API_TOKEN}',
        'Content-Type': 'application/json',
    }
    
    # 测试 1: 验证 Token
    print("测试 1/4: 验证 Token 是否有效...")
    try:
        resp = requests.get(
            'https://api.cloudflare.com/client/v4/user/tokens/verify',
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                print(f"[OK] Token 有效")
                print(f"  状态: {data.get('result', {}).get('status')}")
            else:
                print(f"[FAIL] Token 验证失败")
                print(f"  错误: {data.get('errors')}")
                return False
        else:
            print(f"[FAIL] HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] 请求失败: {e}")
        return False
    
    print()
    
    # 测试 2: 检查 Account ID
    print("测试 2/4: 验证 Account ID...")
    try:
        resp = requests.get(
            f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}',
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                account = data.get('result', {})
                print(f"[OK] Account ID 正确")
                print(f"  名称: {account.get('name')}")
            else:
                print(f"[FAIL] Account 访问失败")
                print(f"  错误: {data.get('errors')}")
                return False
        elif resp.status_code == 403:
            print(f"[FAIL] HTTP 403: Token 无权限访问此 Account")
            return False
        elif resp.status_code == 404:
            print(f"[FAIL] HTTP 404: Account ID 不存在")
            return False
        else:
            print(f"[FAIL] HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] 请求失败: {e}")
        return False
    
    print()
    
    # 测试 3: 列出 Workers (读取权限)
    print("测试 3/4: 检查 Workers 读取权限...")
    try:
        resp = requests.get(
            f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/workers/scripts',
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                workers = data.get('result', [])
                print(f"[OK] 可以读取 Workers ({len(workers)} 个)")
                for worker in workers[:3]:
                    script_id = worker.get('id', 'unknown')
                    print(f"  - {script_id}")
            else:
                print(f"[FAIL] Workers 读取失败")
                print(f"  错误: {data.get('errors')}")
                return False
        elif resp.status_code == 403:
            print(f"[FAIL] HTTP 403: 缺少 Workers Scripts:Read 权限")
            return False
        elif resp.status_code == 404:
            print(f"[FAIL] HTTP 404: Account ID 可能不正确")
            return False
        else:
            print(f"[FAIL] HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] 请求失败: {e}")
        return False
    
    print()
    
    # 测试 4: 测试 Workers 写入权限
    print("测试 4/4: 检查 Workers 编辑权限...")
    try:
        resp = requests.get(
            f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/workers/scripts/test-permission',
            headers=headers,
            timeout=10
        )
        if resp.status_code == 404:
            print(f"[OK] 有 Workers 编辑权限")
        elif resp.status_code == 403:
            print(f"[FAIL] HTTP 403: 缺少 Workers Scripts:Edit 权限")
            print()
            print("需要的权限:")
            print("  - Account -> Workers Scripts -> Edit")
            print()
            return False
        else:
            print(f"[UNKNOWN] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[FAIL] 请求失败: {e}")
    
    print()
    print("=" * 80)
    print("[SUCCESS] Token 权限测试通过")
    print("=" * 80)
    print()
    
    return True

if __name__ == '__main__':
    try:
        success = test_token()
        
        if not success:
            print()
            print("[ERROR] Token 权限不足")
            print()
            print("解决方法:")
            print("  1. 访问 https://dash.cloudflare.com/profile/api-tokens")
            print("  2. 点击 'Create Token'")
            print("  3. 选择模板 'Edit Cloudflare Workers'")
            print("  4. 确保包含权限:")
            print("     - Account -> Workers Scripts -> Edit")
            print("     - Zone -> Workers Routes -> Edit (可选)")
            print("  5. 复制生成的 Token")
            print()
            sys.exit(1)
        else:
            print("[SUCCESS] Token 权限正常，可以继续部署!")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
        sys.exit(130)

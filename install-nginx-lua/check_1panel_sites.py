#!/usr/bin/env python3
"""
检查 1Panel 中的站点列表
用于诊断为什么找不到指定的域名
"""
import hashlib
import time
import requests
import warnings

# 配置（从 fangyu_scripts.py 复制）
PANEL_URL = "http://198.200.42.128:31384"
PANEL_KEY = "pWAEY3ldk1phmLLAHgnmibxRgABMoBwZ"

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

def generate_signature():
    """生成 1Panel API 签名"""
    timestamp = str(int(time.time()))
    sign_str = f"1panel{PANEL_KEY}{timestamp}"
    signature = hashlib.md5(sign_str.encode()).hexdigest()
    return signature, timestamp

def get_headers():
    """获取请求头"""
    signature, timestamp = generate_signature()
    return {
        "Content-Type": "application/json",
        "1Panel-Token": signature,
        "1Panel-Timestamp": timestamp,
    }

def list_all_websites():
    """列出所有网站"""
    print("=" * 80)
    print("查询 1Panel 中的所有站点")
    print("=" * 80)
    print()
    
    all_websites = []
    page = 1
    
    while page <= 10:  # 最多查询 10 页
        headers = get_headers()
        
        resp = requests.post(
            f"{PANEL_URL}/api/v2/websites/search",
            headers=headers,
            json={
                "name": "",  # 空字符串表示查询所有
                "page": page,
                "pageSize": 50,
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
                print(f"第 {page} 页: 找到 {len(items)} 个站点")
                
                if len(items) < 50:
                    break
                page += 1
            else:
                break
        else:
            print(f"API 调用失败: HTTP {resp.status_code}")
            break
    
    print()
    print(f"共找到 {len(all_websites)} 个站点:")
    print("=" * 80)
    print()
    
    if not all_websites:
        print("⚠️  未找到任何站点！")
        print()
        print("可能的原因:")
        print("  1. 1Panel 中确实没有创建任何站点")
        print("  2. API 密钥权限不足")
        print("  3. 1Panel 连接失败")
        return []
    
    for i, site in enumerate(all_websites, 1):
        print(f"{i}. 主域名: {site.get('primaryDomain', 'N/A')}")
        print(f"   站点 ID: {site.get('id', 'N/A')}")
        print(f"   别名: {site.get('alias', 'N/A')}")
        print(f"   站点路径: {site.get('sitePath', 'N/A')}")
        
        # 显示所有绑定的域名
        domains = site.get('domains', [])
        if domains:
            print(f"   绑定域名: {', '.join([d.get('domain', '') for d in domains])}")
        
        print()
    
    return all_websites

def search_specific_domain(domain):
    """搜索特定域名"""
    print("=" * 80)
    print(f"搜索域名: {domain}")
    print("=" * 80)
    print()
    
    headers = get_headers()
    
    resp = requests.post(
        f"{PANEL_URL}/api/v2/websites/search",
        headers=headers,
        json={
            "name": domain,
            "page": 1,
            "pageSize": 50,
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
            print(f"✓ 找到 {len(items)} 个匹配的站点:")
            for site in items:
                print(f"  - {site.get('primaryDomain')} (ID: {site.get('id')})")
            return items
        else:
            print(f"✗ 未找到匹配 '{domain}' 的站点")
            return []
    else:
        print(f"✗ API 调用失败: HTTP {resp.status_code}")
        return []

if __name__ == "__main__":
    print()
    
    # 1. 列出所有站点
    all_sites = list_all_websites()
    
    # 2. 搜索指定域名
    if all_sites:
        print()
        target_domain = "waybifair.shop"
        search_specific_domain(target_domain)
        
        # 尝试其他可能的匹配
        print()
        print("尝试模糊匹配:")
        for site in all_sites:
            primary = site.get('primaryDomain', '')
            if 'waybifair' in primary.lower() or 'shop' in primary.lower():
                print(f"  可能匹配: {primary}")

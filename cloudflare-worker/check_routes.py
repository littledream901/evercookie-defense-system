#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cloudflare Worker 路由管理工具"""

import argparse
import requests
import sys
from typing import List, Dict, Optional

# ========== 配置区 ==========
CF_API_TOKEN = "cfut_UKNOKoJXqxwWcHS1ypApN3t0sPzgX9qhCjPYjaK3f84c00ca"
CF_ZONE_ID = "6fc641a070d7943cc2c43ca1487f1486"
DEFAULT_WORKER = "fangyu-defense"
# ============================


class Colors:
    """ANSI 颜色代码"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


class RouteManager:
    """Worker 路由管理器"""
    
    def __init__(self, api_token: str, zone_id: str):
        self.api_token = api_token
        self.zone_id = zone_id
        self.base_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/workers/routes"
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }
    
    def list_routes(self) -> List[Dict]:
        """列出所有路由"""
        response = requests.get(self.base_url, headers=self.headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('result', [])
        else:
            raise RuntimeError(f"查询失败 (HTTP {response.status_code}): {response.text}")
    
    def add_route(self, pattern: str, worker_name: str) -> Dict:
        """添加新路由"""
        payload = {
            'pattern': pattern,
            'script': worker_name
        }
        
        response = requests.post(self.base_url, headers=self.headers, json=payload)
        
        if response.status_code in (200, 201):
            data = response.json()
            if data.get('success'):
                return data.get('result', {})
            else:
                errors = data.get('errors', [])
                error_msg = '; '.join([f"{e.get('code')}: {e.get('message')}" for e in errors])
                raise RuntimeError(f"添加失败: {error_msg}")
        else:
            raise RuntimeError(f"添加失败 (HTTP {response.status_code}): {response.text}")
    
    def delete_route(self, route_id: str) -> bool:
        """删除路由"""
        url = f"{self.base_url}/{route_id}"
        response = requests.delete(url, headers=self.headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('success', False)
        else:
            raise RuntimeError(f"删除失败 (HTTP {response.status_code}): {response.text}")
    
    def find_route_by_pattern(self, pattern: str) -> Optional[Dict]:
        """根据 pattern 查找路由"""
        routes = self.list_routes()
        for route in routes:
            if route.get('pattern') == pattern:
                return route
        return None


def cmd_list(manager: RouteManager):
    """列出所有路由"""
    try:
        routes = manager.list_routes()
        
        if not routes:
            print(f"{Colors.YELLOW}❌ 没有找到任何路由规则{Colors.END}")
            return
        
        print(f"{Colors.GREEN}✅ 找到 {len(routes)} 条路由规则:{Colors.END}\n")
        
        for idx, route in enumerate(routes, 1):
            print(f"{Colors.BLUE}路由 {idx}:{Colors.END}")
            print(f"  ID:      {route.get('id')}")
            print(f"  Pattern: {route.get('pattern')}")
            print(f"  Worker:  {route.get('script')}")
            print(f"  启用:    {'是' if route.get('enabled', True) else '否'}")
            print()
    
    except Exception as e:
        print(f"{Colors.RED}❌ 错误: {e}{Colors.END}")
        sys.exit(1)


def cmd_add(manager: RouteManager, pattern: str, worker: str):
    """添加新路由"""
    try:
        # 检查是否已存在
        existing = manager.find_route_by_pattern(pattern)
        if existing:
            print(f"{Colors.YELLOW}⚠️  路由已存在:{Colors.END}")
            print(f"  Pattern: {existing.get('pattern')}")
            print(f"  Worker:  {existing.get('script')}")
            print(f"  ID:      {existing.get('id')}")
            
            response = input("\n是否要删除旧路由并添加新路由? (y/N): ")
            if response.lower() != 'y':
                print("操作已取消")
                return
            
            print(f"\n{Colors.BLUE}[步骤]{Colors.END} 删除旧路由...")
            manager.delete_route(existing['id'])
            print(f"{Colors.GREEN}✅ 旧路由已删除{Colors.END}")
        
        print(f"\n{Colors.BLUE}[步骤]{Colors.END} 添加新路由...")
        result = manager.add_route(pattern, worker)
        
        print(f"{Colors.GREEN}✅ 路由添加成功:{Colors.END}")
        print(f"  ID:      {result.get('id')}")
        print(f"  Pattern: {result.get('pattern')}")
        print(f"  Worker:  {result.get('script')}")
    
    except Exception as e:
        print(f"{Colors.RED}❌ 错误: {e}{Colors.END}")
        sys.exit(1)


def cmd_delete(manager: RouteManager, pattern: Optional[str], route_id: Optional[str]):
    """删除路由"""
    try:
        # 确定要删除的路由
        if route_id:
            target_id = route_id
            print(f"{Colors.BLUE}[步骤]{Colors.END} 删除路由 ID: {route_id}")
        elif pattern:
            route = manager.find_route_by_pattern(pattern)
            if not route:
                print(f"{Colors.YELLOW}❌ 未找到匹配的路由: {pattern}{Colors.END}")
                return
            target_id = route['id']
            print(f"{Colors.BLUE}[步骤]{Colors.END} 删除路由:")
            print(f"  Pattern: {route.get('pattern')}")
            print(f"  Worker:  {route.get('script')}")
            print(f"  ID:      {route.get('id')}")
        else:
            print(f"{Colors.RED}❌ 必须提供 --pattern 或 --id{Colors.END}")
            sys.exit(1)
        
        # 确认删除
        response = input("\n确认删除? (y/N): ")
        if response.lower() != 'y':
            print("操作已取消")
            return
        
        # 执行删除
        success = manager.delete_route(target_id)
        
        if success:
            print(f"{Colors.GREEN}✅ 路由已删除{Colors.END}")
        else:
            print(f"{Colors.RED}❌ 删除失败{Colors.END}")
    
    except Exception as e:
        print(f"{Colors.RED}❌ 错误: {e}{Colors.END}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Cloudflare Worker 路由管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 列出所有路由
  python check_routes.py list
  
  # 添加新路由
  python check_routes.py add --pattern "example.com/*" --worker fangyu-defense
  
  # 删除路由（通过 pattern）
  python check_routes.py delete --pattern "example.com/*"
  
  # 删除路由（通过 ID）
  python check_routes.py delete --id abc123xyz
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # list 命令
    subparsers.add_parser('list', help='列出所有路由')
    
    # add 命令
    parser_add = subparsers.add_parser('add', help='添加新路由')
    parser_add.add_argument('--pattern', required=True, help='路由模式（如 example.com/*）')
    parser_add.add_argument('--worker', default=DEFAULT_WORKER, help=f'Worker 名称（默认: {DEFAULT_WORKER}）')
    
    # delete 命令
    parser_delete = subparsers.add_parser('delete', help='删除路由')
    group = parser_delete.add_mutually_exclusive_group(required=True)
    group.add_argument('--pattern', help='路由模式')
    group.add_argument('--id', help='路由 ID')
    
    args = parser.parse_args()
    
    # 如果没有提供命令，默认执行 list
    if not args.command:
        args.command = 'list'
    
    # 初始化管理器
    manager = RouteManager(CF_API_TOKEN, CF_ZONE_ID)
    
    # 执行命令
    if args.command == 'list':
        cmd_list(manager)
    elif args.command == 'add':
        cmd_add(manager, args.pattern, args.worker)
    elif args.command == 'delete':
        cmd_delete(manager, args.pattern, args.id)
    else:
        parser.print_help()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}用户中断操作{Colors.END}")
        sys.exit(130)
    except Exception as e:
        print(f"{Colors.RED}❌ 未预期的错误: {e}{Colors.END}")
        sys.exit(1)

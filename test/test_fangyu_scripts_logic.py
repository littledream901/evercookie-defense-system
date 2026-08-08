#!/usr/bin/env python3
"""
测试 fangyu_scripts.py 的核心业务逻辑
"""
import importlib.util
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location(
    "fangyu_scripts",
    project_root / "nginx-dep" / "fangyu_scripts.py",
)
fangyu_scripts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fangyu_scripts)

NginxConfigGenerator = fangyu_scripts.NginxConfigGenerator
NginxConfManager = fangyu_scripts.NginxConfManager
NginxResolverConfigurator = fangyu_scripts.NginxResolverConfigurator


class _MockApiClient:
    def __init__(self, content_map=None):
        self.content_map = content_map or {}

    def get_container_file_content(self, container_id, path):
        return self.content_map.get(path)

    def upload_file_to_container(self, *args, **kwargs):
        return True

    def check_file_exists(self, *args, **kwargs):
        return True

    def exec_container_command(self, *args, **kwargs):
        return True, "exists", ""


def test_check_lua_config_ignores_comments():
    content = """# lua_package_path "/commented/?.lua;;";
http {
    # lua_package_cpath "/commented/?.so;;";
    lua_package_path "/real/?.lua;;";
    lua_package_cpath "/real/?.so;;";
}"""
    manager = NginxConfManager(_MockApiClient({"/usr/local/openresty/nginx/conf/nginx.conf": content}))
    assert manager.check_lua_config("cid") is True


def test_extract_server_name_prefers_real_value():
    content = """server {
    server_name wayaffair.shop;
    location / {
        proxy_pass http://upstream;
    }
}"""
    assert fangyu_scripts._extract_server_name(content) == "wayaffair.shop"


def test_generate_blocks_cleans_values():
    vars_block, access_lua, body_filter = NginxConfigGenerator.generate_config_blocks(
        "`wayaefair.shop`",
        " site_1 ",
        " 1 ",
        " secret ",
        " `https://gateway.foxfingerlab.com` ",
    )
    assert 'https://gateway.foxfingerlab.com' in vars_block
    assert '`' not in vars_block
    assert '/www/sites/wayaefair.shop/lua/defense.lua' in access_lua
    assert 'proxy_set_header Accept-Encoding "";' in access_lua
    assert 'proxy_hide_header Content-Encoding;' in access_lua
    assert 'set_real_ip_from 173.245.48.0/20;' in vars_block
    assert 'real_ip_header CF-Connecting-IP;' in vars_block
    assert 'real_ip_recursive on;' in vars_block
    assert 'body_filter_by_lua_block' in body_filter
    assert 'safe_snippet = snippet:gsub("%%", "%%%%")' in body_filter
    assert 'string.gsub(chunk, "</head>", safe_snippet .. "</head>", 1)' in body_filter


def test_add_lua_config_uses_http_block():
    content = """events {}
http {
    include mime.types;
}
server {
    listen 80;
}"""
    manager = NginxConfManager(_MockApiClient({"/usr/local/openresty/nginx/conf/nginx.conf": content}))
    assert manager.add_lua_config("cid") is True


def test_inject_vars_block_limited_to_server_block():
    config = """server {
    server_name example.com;
    location / {
        proxy_pass http://upstream;
    }
}

server {
    server_name other.com;
}"""
    result = NginxConfigGenerator.inject_vars_block(config, "    set $fangyu_site_id \"site_1\";")
    assert result.count('set $fangyu_site_id') == 1
    assert 'other.com' in result


def test_inject_access_lua_targets_first_server_block():
    config = """server {
    server_name example.com;
    set $fy_sdk_snippet "";
    set $fy_server_token "";
    location / {
        proxy_pass http://upstream;
    }
}

server {
    server_name other.com;
}"""
    result = NginxConfigGenerator.inject_access_lua(config, "        access_by_lua_file /www/sites/example.com/lua/defense.lua;")
    assert result.count('access_by_lua_file') == 1
    assert result.index('location / {') < result.index('access_by_lua_file') < result.index('proxy_pass http://upstream;')


def test_inject_body_filter_first_server_only():
    config = """server {
    server_name example.com;
    location / {
        proxy_pass http://upstream;
    }
}

server {
    server_name other.com;
}"""
    result = NginxConfigGenerator.inject_body_filter(config, "        body_filter_by_lua_block {\n        }")
    assert result.count('body_filter_by_lua_block') == 1
    lines = result.split('\n')
    server_start, server_end = fangyu_scripts._find_first_block(lines, 'server')
    location_start, location_end = fangyu_scripts._find_location_block(lines, server_start, server_end)
    body_filter_line = next(i for i, line in enumerate(lines) if 'body_filter_by_lua_block' in line)
    assert location_start < body_filter_line < location_end


def test_remove_old_config_ignores_comments():
    config = """# set $fangyu_site_id \"old\";
set_real_ip_from 173.245.48.0/20;
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
server {
    # access_by_lua_file /tmp/defense.lua;
    proxy_set_header Accept-Encoding "";
    proxy_hide_header Content-Encoding;
    body_filter_by_lua_block {
    }
    set $fangyu_site_id \"real\";
}"""
    result = NginxConfigGenerator.remove_old_fangyu_config(config)
    active = '\n'.join(fangyu_scripts._strip_nginx_comment(line) for line in result.split('\n'))
    assert 'body_filter_by_lua_block' not in active
    assert 'set $fangyu_site_id' not in active
    assert 'proxy_set_header Accept-Encoding' not in active
    assert 'proxy_hide_header Content-Encoding' not in active
    assert 'set_real_ip_from' not in active
    assert 'real_ip_header' not in active
    assert 'real_ip_recursive' not in active


def test_resolver_check_ignores_comments():
    content = """http {
    # resolver 8.8.8.8;
    include mime.types;
}"""
    manager = NginxResolverConfigurator(_MockApiClient({"/usr/local/openresty/nginx/conf/nginx.conf": content}))
    assert manager.ensure_resolver_configured("cid") is True


def run_all_tests():
    tests = [
        test_check_lua_config_ignores_comments,
        test_generate_blocks_cleans_values,
        test_add_lua_config_uses_http_block,
        test_inject_vars_block_limited_to_server_block,
        test_inject_access_lua_targets_first_server_block,
        test_inject_body_filter_first_server_only,
        test_remove_old_config_ignores_comments,
        test_resolver_check_ignores_comments,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    run_all_tests()

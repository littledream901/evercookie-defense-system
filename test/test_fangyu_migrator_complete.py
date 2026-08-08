#!/usr/bin/env python3
"""
完整的 fangyu_template_migrator.py 模块化测试
覆盖所有业务逻辑类的功能
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
NGINX_DEP_DIR = PROJECT_ROOT / "nginx-install"
sys.path.insert(0, str(NGINX_DEP_DIR))

from fangyu_template_migrator import (
    Colors,
    ContainerManager,
    DefenseLuaDeployer,
    FangyuInstaller,
    FangyuTemplateMigrator,
    InstallationTester,
    Logger,
    NginxConfigGenerator,
    NginxConfigManager,
    NginxConfManager,
    NginxResolverConfigurator,
    OnePanelAPIClient,
    _real_ip_config_path,
    RealIpConfigDeployer,
    _real_ip_config_content,
)


class TestFangyuTemplateMigrator:
    """测试 FangyuTemplateMigrator 配置迁移逻辑"""

    def test_migrate_config_injects_fangyu_blocks(self):
        """测试配置迁移注入 Fangyu 块"""
        original = """server {
    listen 80;
    server_name example.com;
    
    location / {
        proxy_pass http://backend;
    }
}"""
        result = FangyuTemplateMigrator.migrate_config(
            original, "site123", "app456", "secret789", "https://gateway.com"
        )
        
        assert "set $fangyu_site_id" in result
        assert "set $fangyu_app_id" in result
        assert "set $fangyu_app_secret" in result
        assert f"include {_real_ip_config_path('example.com')};" in result
        assert "set_real_ip_from" not in result
        assert "access_by_lua_file" in result
        assert "body_filter_by_lua_block" in result
        assert "proxy_pass http://backend" in result  # 保留原有配置

    def test_migrate_config_removes_old_fangyu_blocks(self):
        """测试配置迁移清除旧 Fangyu 块"""
        original = """server {
    listen 80;
    server_name example.com;
    
    # 旧的 Fangyu 配置
    set $fangyu_site_id "old_site";
    
    location / {
        access_by_lua_file /old/defense.lua;
        proxy_pass http://backend;
    }
}"""
        result = FangyuTemplateMigrator.migrate_config(
            original, "new_site", "new_app", "new_secret", "https://new-gateway.com"
        )
        
        assert '"old_site"' not in result
        assert '"new_site"' in result
        assert f"include {_real_ip_config_path('example.com')};" in result
        assert 'set_real_ip_from' not in result
        assert "/old/defense.lua" not in result

    def test_real_ip_config_content(self):
        content = _real_ip_config_content()
        assert "set_real_ip_from 173.245.48.0/20;" in content
        assert "set_real_ip_from 2c0f:f248::/32;" in content
        assert "real_ip_header CF-Connecting-IP;" in content
        assert "real_ip_recursive on;" in content


class TestOnePanelAPIClient:
    """测试 OnePanelAPIClient API 客户端"""

    @patch('requests.Session')
    def test_search_containers(self, mock_session_class):
        """测试容器搜索 API"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'code': 200,
            'data': {
                'items': [
                    {'containerID': 'abc123', 'name': 'openresty'},
                    {'containerID': 'def456', 'name': 'nginx'}
                ],
                'total': 2
            }
        }
        mock_session.post.return_value = mock_response
        
        client = OnePanelAPIClient("http://localhost:8080", "test-key")
        client.session = mock_session
        
        results = client.search_containers("openresty")
        
        assert len(results) == 2
        assert results[0]['containerID'] == 'abc123'
        mock_session.post.assert_called_once()

    @patch('requests.Session')
    def test_exec_container_command(self, mock_session_class):
        """测试容器命令执行 API"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'code': 200,
            'data': {
                'exitCode': 0,
                'stdout': 'command output',
                'stderr': ''
            }
        }
        mock_session.post.return_value = mock_response
        
        client = OnePanelAPIClient("http://localhost:8080", "test-key")
        client.session = mock_session
        
        success, stdout, stderr = client.exec_container_command(
            'container123', 'ls -la'
        )
        
        assert success is True
        assert stdout == 'command output'
        assert stderr == ''


class TestContainerManager:
    """测试 ContainerManager 容器管理逻辑"""

    def test_find_openresty_container_success(self):
        """测试查找 OpenResty 容器成功"""
        mock_client = Mock(spec=OnePanelAPIClient)
        mock_client.search_containers.return_value = [
            {'containerID': 'openresty123', 'name': '1panel-openresty-jfKL', 'state': 'running'}
        ]
        
        manager = ContainerManager(mock_client)
        name, container_id = manager.find_openresty_container()
        
        assert name == '1panel-openresty-jfKL'
        assert container_id == 'openresty123'

    def test_check_lua_dependencies(self):
        """测试 Lua 依赖检查 - 不验证内部实现细节"""
        mock_client = Mock(spec=OnePanelAPIClient)
        
        manager = ContainerManager(mock_client)
        # 不应该抛出异常即可
        try:
            manager.check_lua_dependencies('container123')
        except Exception:
            pytest.fail("check_lua_dependencies should not raise exception")


class TestDefenseLuaDeployer:
    """测试 DefenseLuaDeployer 部署逻辑"""

    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_find_defense_lua_source(self, mock_getsize, mock_exists):
        """测试查找 defense.lua 源文件"""
        mock_exists.return_value = True
        mock_getsize.return_value = 5000  # 文件大于 500 字节
        
        mock_client = Mock(spec=OnePanelAPIClient)
        deployer = DefenseLuaDeployer(mock_client)
        
        source = deployer._find_defense_lua_source()
        
        assert source is not None
        assert 'defense.lua' in source

    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_deploy_success(self, mock_getsize, mock_exists):
        """测试部署 defense.lua 成功"""
        mock_exists.return_value = True
        mock_getsize.return_value = 5000
        
        mock_client = Mock(spec=OnePanelAPIClient)
        mock_client.upload_file_to_container.return_value = True
        
        deployer = DefenseLuaDeployer(mock_client)
        result = deployer.deploy('example.com', 'container123')
        
        assert result is True
        mock_client.upload_file_to_container.assert_called_once()


class TestRealIpConfigDeployer:
    def test_deploy_real_ip_config(self):
        mock_client = Mock(spec=OnePanelAPIClient)
        mock_client.upload_file_to_container.return_value = True

        deployer = RealIpConfigDeployer(mock_client)
        result = deployer.deploy('example.com', 'container123')

        assert result is True
        args = mock_client.upload_file_to_container.call_args.args
        assert args[0] == 'container123'
        assert args[2] == '/www/sites/example.com/lua'


class TestNginxConfigGenerator:
    """测试 NginxConfigGenerator 配置生成逻辑"""

    def test_generate_config_blocks(self):
        """测试生成 Nginx 配置块"""
        vars_block, access_lua, body_filter = NginxConfigGenerator.generate_config_blocks(
            'example.com', 'site123', 'app456', 'secret789', 'https://gateway.com'
        )
        
        assert 'set $fangyu_gateway_url' in vars_block
        assert 'set $fangyu_site_id' in vars_block
        assert 'set $fangyu_app_id' in vars_block
        assert f'include {_real_ip_config_path("example.com")};' in vars_block
        assert 'set_real_ip_from' not in vars_block
        assert 'access_by_lua_file' in access_lua
        assert '/www/sites/example.com/lua/defense.lua' in access_lua
        assert 'body_filter_by_lua_block' in body_filter
        assert 'fy_sdk_snippet' in body_filter


class TestNginxConfigManager:
    """测试 NginxConfigManager 网站配置管理"""

    @patch('sys.exit')
    def test_update_website_config(self, mock_exit):
        """测试更新网站配置"""
        mock_client = Mock(spec=OnePanelAPIClient)
        mock_client.search_websites.return_value = [
            {'id': 1, 'primaryDomain': 'example.com', 'runtimeID': 1}
        ]
        # 注意：实际方法名是 get_container_file_content，不是 get_website_nginx_config
        mock_client.get_container_file_content.return_value = """server {
    listen 80;
    server_name example.com;
    location / {
        proxy_pass http://backend;
    }
}"""
        mock_client.update_website_nginx_config.return_value = True
        mock_client.check_file_exists.return_value = True
        # Mock exec_container_command 返回元组
        mock_client.exec_container_command.return_value = (True, 'syntax is ok', '')
        
        manager = NginxConfigManager(mock_client)
        config_path = manager.update_website_config(
            'example.com', 'site123', 'app456', 'secret789',
            'https://gateway.com', 'container123', skip_ssl_check=True
        )
        
        assert '/www/sites/example.com/conf/example.com.conf' in config_path or '/usr/local/openresty/nginx/conf/conf.d/example.com.conf' in config_path
        mock_client.update_website_nginx_config.assert_called_once()


class TestInstallationTester:
    """测试 InstallationTester 安装验证逻辑"""

    def test_test_defense_lua(self):
        """测试 defense.lua 文件存在检查"""
        mock_client = Mock(spec=OnePanelAPIClient)
        mock_client.get_container_file_content.return_value = "a" * 15000  # 大于 10000 字节
        
        tester = InstallationTester(mock_client)
        result = tester._test_defense_lua('example.com', 'container123')
        
        assert result is True

    def test_test_nginx_config_syntax(self):
        mock_client = Mock(spec=OnePanelAPIClient)
        config_content = """server {
    listen 80;
    server_name example.com;
    include /www/sites/example.com/lua/fangyu_real_ip.conf;
    
    set $fangyu_gateway_url "https://gateway.com";
    set $fangyu_site_id "site_123";
    set $fangyu_app_id "app_1";
    set $fangyu_app_secret "secret_abc";
    
    location / {
        access_by_lua_file /www/sites/example.com/lua/defense.lua;
        proxy_pass http://backend;
        body_filter_by_lua_block {
            local snippet = ngx.var.fy_sdk_snippet
        }
    }
}"""
        def get_content(_, path):
            if path == _real_ip_config_path('example.com'):
                return _real_ip_config_content()
            return config_content

        mock_client.get_container_file_content.side_effect = get_content
        mock_client.exec_container_command.return_value = (True, 'syntax is ok', '')

        tester = InstallationTester(mock_client)
        result = tester._test_nginx_config('container123', '/www/sites/example.com/conf/example.com.conf', 'example.com')
        
        # 应该返回 True（配置完整且语法正确）
        assert result is True

    def test_display_results_method_exists(self):
        """测试 _display_results 方法存在"""
        tester = InstallationTester(Mock())
        
        # 所有测试通过
        results = {
            'defense_lua': True,
            'nginx_config': True,
            'no_errors': True,
            'website_ok': True,
            'defense_active': True
        }
        # 方法应该存在并可调用
        assert hasattr(tester, '_display_results')
        result = tester._display_results(results)
        assert isinstance(result, bool)


class TestFangyuInstaller:
    """测试 FangyuInstaller 主安装器"""

    def test_installer_initialization(self):
        """测试安装器初始化"""
        with patch('fangyu_template_migrator.OnePanelAPIClient'):
            installer = FangyuInstaller('http://localhost:8080', 'test-key')
            
            assert installer.api_client is not None
            assert installer.container_manager is not None
            assert installer.deployer is not None
            assert installer.main_conf_manager is not None
            assert installer.resolver_config is not None
            assert installer.nginx_manager is not None
            assert installer.tester is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

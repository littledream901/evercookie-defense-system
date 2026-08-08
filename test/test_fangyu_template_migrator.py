from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent.parent / "nginx-install"))
import fangyu_template_migrator as migrator_module

FangyuTemplateMigrator = migrator_module.FangyuTemplateMigrator
_real_ip_config_path = migrator_module._real_ip_config_path


def test_migrate_config_keeps_original_server_and_injects_fangyu_blocks():
    config = """server {
    listen 443 ssl;
    server_name wayaffair.shop;
    location / {
        proxy_pass http://127.0.0.1:8081;
    }
}"""

    result = FangyuTemplateMigrator.migrate_config(
        config,
        "site_eba8689a",
        "1",
        "secret_value",
        "https://gateway.foxfingerlab.com",
    )

    assert result.count("set $fangyu_site_id") == 1
    assert f"include {_real_ip_config_path('wayaffair.shop')};" in result
    assert "set_real_ip_from" not in result
    assert result.count("access_by_lua_file") == 1
    assert result.count("body_filter_by_lua_block") == 1
    assert "server_name wayaffair.shop;" in result
    assert "proxy_pass http://127.0.0.1:8081;" in result
    assert 'https://gateway.foxfingerlab.com' in result


def test_migrate_config_replaces_old_fangyu_blocks():
    config = """server {
    server_name wayaffair.shop;
    set_real_ip_from 173.245.48.0/20;
    real_ip_header CF-Connecting-IP;
    real_ip_recursive on;
    set $fangyu_gateway_url  "old";
    set $fangyu_site_id      "old";
    set $fangyu_app_id       "old";
    set $fangyu_app_secret   "old";
    set $fangyu_fail_mode    "open";
    set $fangyu_sdk_inject   "on";
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";
    set $fy_sdk_snippet      "";
    set $fy_server_token     "";
    location / {
        access_by_lua_file /www/sites/wayaffair.shop/lua/defense.lua;
        proxy_set_header Accept-Encoding "";
        proxy_hide_header Content-Encoding;
        body_filter_by_lua_block {
            local snippet = ngx.var.fy_sdk_snippet
        }
    }
}"""

    result = FangyuTemplateMigrator.migrate_config(
        config,
        "site_eba8689a",
        "1",
        "secret_value",
        "https://gateway.foxfingerlab.com",
    )

    assert result.count("set $fangyu_site_id") == 1
    assert f"include {_real_ip_config_path('wayaffair.shop')};" in result
    assert "set_real_ip_from" not in result
    assert "real_ip_header" not in result
    assert "real_ip_recursive" not in result
    assert result.count("access_by_lua_file") == 1
    assert result.count("body_filter_by_lua_block") == 1
    assert "old" not in result


def test_migrate_config_requires_server_name():
    config = """location / {
    proxy_pass http://127.0.0.1:8081;
}"""

    try:
        FangyuTemplateMigrator.migrate_config(
            config,
            "site_eba8689a",
            "1",
            "secret_value",
            "https://gateway.foxfingerlab.com",
        )
    except ValueError as exc:
        assert "server_name" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_real_ip_config_content_keeps_trusted_proxy_rules():
    content = migrator_module._real_ip_config_content()
    assert "set_real_ip_from 173.245.48.0/20;" in content
    assert "set_real_ip_from 2c0f:f248::/32;" in content
    assert "real_ip_header CF-Connecting-IP;" in content
    assert "real_ip_recursive on;" in content


def test_migrate_config_with_complex_existing_fangyu():
    complex_original = """server {
    server_name multiblock.com;
    set_real_ip_from 173.245.48.0/20;
    real_ip_header CF-Connecting-IP;
    real_ip_recursive on;
    set $fangyu_gateway_url  "old";
    set $fangyu_site_id      "old";
    set $fangyu_app_id       "old";
    set $fangyu_app_secret   "old";
    set $fangyu_fail_mode    "open";
    set $fangyu_sdk_inject   "on";
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";
    set $fy_sdk_snippet      "";
    set $fy_server_token     "";
    location / {
        access_by_lua_file /www/sites/multiblock.com/lua/defense.lua;
        proxy_set_header Accept-Encoding "";
        proxy_hide_header Content-Encoding;
        body_filter_by_lua_block {
            local snippet = ngx.var.fy_sdk_snippet
        }
    }
}"""
    result = FangyuTemplateMigrator.migrate_config(complex_original, "new_site", "app_2", "secret_xyz", "https://gw2.example.com")
    assert "server_name multiblock.com;" in result
    assert result.count("set $fangyu_gateway_url") == 1
    assert f"include {_real_ip_config_path('multiblock.com')};" in result
    assert "set_real_ip_from" not in result
    assert "real_ip_header" not in result
    assert "real_ip_recursive" not in result
    assert result.count("access_by_lua_file") == 1

"""SDK 静态分发挂载测试。

覆盖 ``_mount_sdk_static`` 的两条分支，防止两类回归：

1. 目录存在时必须真的能取到文件，且**不被 API Key 中间件拦截**。
   SDK 是要公开发给任意接入站点浏览器的，一旦落进鉴权范围，
   接入方页面会拿到 401 而不是脚本，且现象与 404 很像，不好排查。
2. 目录缺失时只跳过挂载，不能让网关起不来。本地开发通常不预构建 SDK。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import GatewaySettings
from src.main import _mount_sdk_static


def _app_with_sdk_dir(directory: Path) -> FastAPI:
    app = FastAPI()
    settings = GatewaySettings(sdk_static_dir=str(directory))
    _mount_sdk_static(app, settings)
    return app


@pytest.mark.asyncio
async def test_sdk_file_served_when_dir_exists(tmp_path: Path) -> None:
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    (sdk_dir / "sd-sdk.min.js").write_text("console.log('sdk')", encoding="utf-8")

    app = _app_with_sdk_dir(sdk_dir)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/sdk/sd-sdk.min.js")

    assert resp.status_code == 200
    assert "console.log" in resp.text
    # 未携带任何 X-App-Key 也应成功：静态分发不能落进鉴权范围
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_defense_lua_served_from_same_dir(tmp_path: Path) -> None:
    """后台接入指引给的 /sdk/defense.lua 下载链接与 SDK 同目录。"""
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    (sdk_dir / "defense.lua").write_text("-- lua", encoding="utf-8")

    app = _app_with_sdk_dir(sdk_dir)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/sdk/defense.lua")

    assert resp.status_code == 200


def test_missing_dir_skips_mount_without_raising(tmp_path: Path) -> None:
    """目录不存在时不抛异常，也不挂载 /sdk。"""
    app = _app_with_sdk_dir(tmp_path / "does-not-exist")

    assert not any(getattr(r, "name", None) == "sdk" for r in app.routes)


def test_mounted_route_registered(tmp_path: Path) -> None:
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()

    app = _app_with_sdk_dir(sdk_dir)

    assert any(getattr(r, "name", None) == "sdk" for r in app.routes)

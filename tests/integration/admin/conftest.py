"""admin-api 集成测试专用 fixture。

- 通过 alembic 建表 + 灌 seed。
- 通过 httpx.AsyncClient + ASGITransport 打进程内 HTTP 请求。
- 强隔离 sys.path，避免 gateway/worker 的 `src.*` 冲突。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio

_ROOT = Path(__file__).resolve().parents[3]
_ADMIN = _ROOT / "admin-api"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)

_other = {str(_ADMIN.parent / n) for n in ("gateway-api", "worker")}
sys.path[:] = [p for p in sys.path if p not in _other]
if str(_ADMIN) not in sys.path:
    sys.path.insert(0, str(_ADMIN))


@pytest.fixture(scope="session")
def alembic_upgraded(integration_env: dict) -> Iterator[dict]:
    """运行 alembic upgrade head 建表 + 灌 seed。"""
    env = os.environ.copy()
    env["ADMIN_DATABASE_URL"] = integration_env["ADMIN_DATABASE_URL"]
    proc = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(_ADMIN),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"alembic upgrade 失败: {proc.stderr}")
    yield integration_env


@pytest_asyncio.fixture(scope="function")
async def admin_client(alembic_upgraded: dict) -> AsyncIterator:
    """构造 admin-api ASGI 客户端。"""
    from httpx import ASGITransport, AsyncClient

    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://admin.test") as client:
            yield client


@pytest_asyncio.fixture(scope="function")
async def admin_token(admin_client) -> str:
    """使用 seed 默认管理员登录，返回 access token。"""
    resp = await admin_client.post(
        "/v2/auth/login",
        json={"username": "admin", "password": "Admin@fangyu2026"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["access_token"]

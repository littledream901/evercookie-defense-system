"""gateway-api 集成测试专用 fixture。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator

import pytest_asyncio

_ROOT = Path(__file__).resolve().parents[3]
_GATEWAY = _ROOT / "gateway-api"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)

_other = {str(_GATEWAY.parent / n) for n in ("admin-api", "worker")}
sys.path[:] = [p for p in sys.path if p not in _other]
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))


@pytest_asyncio.fixture(scope="function")
async def gateway_client(integration_env: dict) -> AsyncIterator:
    """构造 gateway-api ASGI 客户端。"""
    from httpx import ASGITransport, AsyncClient

    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
            yield client

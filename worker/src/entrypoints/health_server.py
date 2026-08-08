"""Worker 健康探针与 Prometheus 指标 HTTP 服务。

worker 进程不对外提供业务接口，仅暴露 /healthz、/readyz、/metrics。
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from fangyu_shared.clickhouse_manager import ClickHouseManager
from fangyu_shared.metrics import metrics_endpoint
from fangyu_shared.redis_manager import RedisManager


async def _liveness(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _readiness(_: web.Request) -> web.Response:
    redis_ok = await RedisManager.ping()
    ch_ok = await ClickHouseManager.ping() if ClickHouseManager.is_initialized() else False
    status = 200 if redis_ok and ch_ok else 503
    return web.json_response(
        {
            "status": "ok" if redis_ok and ch_ok else "degraded",
            "redis": "ok" if redis_ok else "fail",
            "clickhouse": "ok" if ch_ok else "fail",
        },
        status=status,
    )


async def _metrics(_: web.Request) -> web.Response:
    body, content_type = metrics_endpoint()
    return web.Response(body=body, content_type=content_type)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", _liveness)
    app.router.add_get("/readyz", _readiness)
    app.router.add_get("/metrics", _metrics)
    return app


async def run_health_server(host: str, port: int) -> asyncio.Task[None]:
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    async def _serve_forever() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    return asyncio.create_task(_serve_forever())

"""Gateway API 主入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fangyu_shared.exceptions import register_exception_handlers
from fangyu_shared.logging import RequestContextMiddleware, configure_logging, get_logger
from fangyu_shared.metrics import PrometheusMiddleware
from fangyu_shared.redis_manager import RedisConfig, RedisManager
from fangyu_shared.tracing import setup_tracing

from src.config import GatewaySettings, get_settings
from src.interfaces.http.dependencies import (
    build_app_key_resolver,
    build_decision_service,
    build_health_prober,
    get_app_key_resolver,
    get_decision_service,
    get_gateway_settings,
    get_health_prober,
    get_nonce_store,
    reset_dependencies,
)
from src.interfaces.http.middleware import AppKeyEnforcementMiddleware, DecisionRateLimitMiddleware
from src.interfaces.http.v2 import v2_router

_logger = get_logger("gateway.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: GatewaySettings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format, service_name=settings.service_name)  # type: ignore[arg-type]
    setup_tracing(
        service_name=settings.service_name,
        service_version=settings.version,
        otlp_endpoint=getattr(settings, "otlp_endpoint", None),
        sample_rate=getattr(settings, "trace_sample_rate", 1.0),
    )
    await RedisManager.init(
        RedisConfig(
            url=settings.redis_url,
            max_connections=settings.redis_max_connections,
        )
    )
    build_decision_service()
    build_app_key_resolver()
    _logger.info("gateway_started", version=settings.version, port=settings.port)
    try:
        yield
    finally:
        _logger.info("gateway_shutdown")
        # 先排空在飞的决策事件，再拆依赖、关 Redis。顺序不能换：事件发布已经
        # 从决策关键路径挪到后台任务，此时可能还有若干 XADD 没跑完，先关连接池
        # 等于在每次正常重启时丢掉最后一批事件。
        try:
            drained = await get_decision_service().drain_events()
            if drained:
                _logger.info("decision_events_drained", count=drained)
        except Exception as exc:
            # 排空失败不能挡住关闭流程，否则进程停不下来。
            _logger.warning("decision_events_drain_failed", error=str(exc))
        reset_dependencies()
        await RedisManager.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Fangyu Gateway API",
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Starlette 的中间件是后添加者先执行。这里的顺序保证：
    # RequestContext → Prometheus → AppKeyEnforcement → DecisionRateLimit → 路由
    # 即 API Key 先解析出 app_id，限流才能按 app_id 计数。
    app.add_middleware(DecisionRateLimitMiddleware, redis=RedisManager.get_client)
    app.add_middleware(
        AppKeyEnforcementMiddleware,
        resolver_provider=get_app_key_resolver,
        settings_provider=get_gateway_settings,
        nonce_store_provider=get_nonce_store,
    )
    app.add_middleware(PrometheusMiddleware, service_name=settings.service_name)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(v2_router)
    _mount_sdk_static(app, settings)

    return app


def _mount_sdk_static(app: FastAPI, settings: GatewaySettings) -> None:
    """把 client-sdk 构建产物挂到 ``/sdk``。

    浏览器从 ``https://<网关域名>/sdk/sd-sdk.min.js`` 取 SDK，与决策接口同域，
    省掉一次跨域预检。产物由 gateway-api.Dockerfile 的 sdk-builder 阶段编译。

    这里刻意**不鉴权**：SDK 文件本身是要公开分发给任意接入站点的浏览器的，
    加 API Key 校验等于要求页面先持密钥才能下载脚本，逻辑上不成立。
    ``AppKeyEnforcementMiddleware`` 的保护模式全部以 ``^/v2/`` 锚定，
    ``/sdk/`` 天然落在保护范围之外，无需额外放行。

    目录缺失时只记警告不抛错：本地开发通常不预构建 SDK，
    不应因此让网关起不来。
    """
    static_dir = Path(settings.sdk_static_dir)
    if not static_dir.is_dir():
        _logger.warning("sdk_static_dir_missing", path=str(static_dir))
        return

    app.mount(
        "/sdk",
        StaticFiles(directory=static_dir),
        name="sdk",
    )
    _logger.info("sdk_static_mounted", path=str(static_dir))


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()

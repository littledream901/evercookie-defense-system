"""Gateway API 主入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    return app


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

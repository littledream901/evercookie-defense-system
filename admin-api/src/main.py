"""Admin API 主入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fangyu_shared.clickhouse_manager import ClickHouseConfig, ClickHouseManager
from fangyu_shared.exceptions import register_exception_handlers
from fangyu_shared.logging import RequestContextMiddleware, configure_logging, get_logger
from fangyu_shared.metrics import PrometheusMiddleware
from fangyu_shared.redis_manager import RedisConfig, RedisManager
from fangyu_shared.tracing import setup_tracing

from src.application.services.audit_service import AuditService
from src.config import AdminSettings, get_settings
from src.infrastructure.cache.app_key_sync import AppKeyRedisSync
from src.infrastructure.database import Database
from src.infrastructure.rate_limiter import RateLimiter
from src.infrastructure.repositories.app_repository import AppRepository
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.scheduler import start_scheduler, stop_scheduler
from src.interfaces.http.middleware import AuditLogMiddleware, LoginRateLimitMiddleware

_logger = get_logger("admin.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: AdminSettings = get_settings()
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
    Database.init(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle,
    )
    await ClickHouseManager.init(
        ClickHouseConfig(
            url=settings.clickhouse_url,
            database=settings.clickhouse_database,
            user=settings.clickhouse_user,
            password=settings.clickhouse_password,
        )
    )
    await _bootstrap_app_key_bindings(settings)
    await _bootstrap_threat_intel_sync()
    await _bootstrap_clock_limits_sync()
    start_scheduler(sync_interval_seconds=getattr(settings, "threat_intel_sync_interval", 3600))

    _logger.info("admin_started", version=settings.version, port=settings.port)
    try:
        yield
    finally:
        _logger.info("admin_shutdown")
        stop_scheduler()
        await ClickHouseManager.close()
        await Database.close()
        await RedisManager.close()


async def _bootstrap_app_key_bindings(settings: AdminSettings) -> None:
    """启动时把 DB 中所有 active 应用的 api_key → app_id 映射刷进 Redis。

    保证 gateway 侧的 :class:`AppKeyResolver` 在冷启动后仍能命中缓存，
    并修复历史数据（例如手动写入 DB 但从未走 admin API 的场景）。
    """
    try:
        redis = RedisManager.get_client()
        sync = AppKeyRedisSync(
            redis,
            key_prefix=settings.app_key_redis_prefix,
            ttl_seconds=settings.app_key_redis_ttl_seconds or None,
        )
        async with Database.session() as session:
            repo = AppRepository(session)
            bindings = await repo.list_active_key_bindings()
        for api_key, app_id in bindings:
            await sync.bind(api_key, app_id)
        _logger.info("app_key_bootstrap_done", count=len(bindings))
    except Exception as exc:  # pragma: no cover - 引导失败不阻塞启动
        _logger.error("app_key_bootstrap_failed", error=str(exc))


async def _bootstrap_threat_intel_sync() -> None:
    """启动时做一次威胁情报全量同步到 Redis。"""
    try:
        from src.infrastructure.repositories.threat_intel_repository import ThreatIntelRepository
        from src.infrastructure.threat_intel_sync import ThreatIntelSync
        async with Database.session() as session:
            repo = ThreatIntelRepository(session)
            rows, _ = await repo.list_active(page=1, page_size=100_000)
        ip_by_category: dict[str, list[str]] = {}
        for r in rows:
            ip_by_category.setdefault(r.category, []).append(r.ip)
        await ThreatIntelSync.full_sync(ip_by_category)
        total = sum(len(v) for v in ip_by_category.values())
        _logger.info("threat_intel_bootstrap_done", total=total)
    except Exception as exc:  # pragma: no cover
        _logger.error("threat_intel_bootstrap_failed", error=str(exc))


async def _bootstrap_clock_limits_sync() -> None:
    """启动时把 DB 中所有 Clock 阈值配置全量写入 Redis。"""
    try:
        from src.infrastructure.clock_sync import ClockSync
        from src.infrastructure.repositories.clock_limits_repository import ClockLimitsRepository
        redis = RedisManager.get_client()
        sync = ClockSync(redis)
        async with Database.session() as session:
            repo = ClockLimitsRepository(session)
            rows = await repo.list_all()
        for row in rows:
            await sync.put_limits(row)
        _logger.info("clock_limits_bootstrap_done", count=len(rows))
    except Exception as exc:  # pragma: no cover
        _logger.error("clock_limits_bootstrap_failed", error=str(exc))


async def _record_audit(payload: dict) -> None:
    """审计中间件 fire-and-forget 使用的 recorder：独立 session 完整提交事务。"""
    try:
        async with Database.session() as session:
            repo = AuditLogRepository(session)
            service = AuditService(repo)
            await service.record(**payload)
            await session.commit()
    except Exception as exc:  # pragma: no cover
        _logger.error("audit_record_failed", error=str(exc), path=payload.get("path"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Fangyu Admin API",
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
    app.add_middleware(AuditLogMiddleware, recorder=_record_audit)
    limiter = RateLimiter(RedisManager.get_client)
    app.add_middleware(LoginRateLimitMiddleware, limiter=limiter)
    app.add_middleware(PrometheusMiddleware, service_name=settings.service_name)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    from src.interfaces.http.v2 import v2_router
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

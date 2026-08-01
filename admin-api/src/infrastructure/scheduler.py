"""定时任务调度器。

使用 APScheduler AsyncIOScheduler，在 admin lifespan 中启动/停止。
当前注册任务：
- threat_intel_sync: 每1小时将 DB 中所有活跃情报全量同步到 Redis
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from fangyu_shared.logging import get_logger

from src.infrastructure.database import Database
from src.infrastructure.repositories.threat_intel_repository import ThreatIntelRepository
from src.infrastructure.threat_intel_sync import ThreatIntelSync

_logger = get_logger("admin.scheduler")
_scheduler: AsyncIOScheduler | None = None


async def _sync_threat_intel() -> None:
    try:
        async with Database.session() as session:
            repo = ThreatIntelRepository(session)
            rows, _ = await repo.list_active(page=1, page_size=100_000)
            ip_by_category: dict[str, list[str]] = {}
            for r in rows:
                ip_by_category.setdefault(r.category, []).append(r.ip)
        await ThreatIntelSync.full_sync(ip_by_category)
        total = sum(len(v) for v in ip_by_category.values())
        _logger.info("threat_intel_sync_done", total=total)
    except Exception as exc:
        _logger.error("threat_intel_sync_failed", error=str(exc))


def start_scheduler(sync_interval_seconds: int = 3600) -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _sync_threat_intel,
        trigger=IntervalTrigger(seconds=sync_interval_seconds),
        id="threat_intel_sync",
        name="威胁情报定期同步到 Redis",
        replace_existing=True,
        misfire_grace_time=60,
    )
    _scheduler.start()
    _logger.info("scheduler_started", jobs=len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _logger.info("scheduler_stopped")
    _scheduler = None

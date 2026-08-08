"""定时任务调度器。

使用 APScheduler AsyncIOScheduler，在 admin lifespan 中启动/停止。
当前注册任务：
- threat_intel_sync:   每1小时 DB → Redis 全量同步威胁情报
- intelligence_sync:   每1小时 DB → Redis 全量同步六类维度情报
- external_intel_sync: 每6小时 从 AbuseIPDB / Tor / URLhaus 拉取外部情报
- clock_resync:        每1小时 DB → Redis 全量同步 Clock 阈值（Redis flush 恢复）
- rule_cache_sync:     每5分钟 DB → Redis 全量同步已发布规则缓存
- reputation_intel_feedback: 每6小时 高风险声誉 → biz_intel_ip_profile

声誉分回写 Redis ProfileCache 的周期任务**不在这里**：由 worker 独占执行
（``worker/src/application/writers/reputation_writer.py``）。admin 侧只保留
``POST /threat-intel/sync`` 手动触发，以及 worker 做不到的情报库沉淀。
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


# ---------- 威胁情报 DB→Redis ----------

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


# ---------- 六类维度情报 DB→Redis ----------

async def sync_intelligence() -> dict[str, int]:
    """把六类维度情报全量重推 Redis，供 gateway 决策链路读取。

    同时被启动引导、定时任务与 CRUD 写操作后触发复用。
    """
    from src.application.services.intel_service import IntelService
    from src.infrastructure.intel_sync import IntelSync
    from src.infrastructure.repositories.intel_repository import IntelType

    rows_by_type: dict[str, list[dict]] = {}
    async with Database.session() as session:
        service = IntelService(session)
        for intel_type in IntelType:
            rows_by_type[intel_type.value] = await service.get_all_active(intel_type)
    return await IntelSync.sync_all(rows_by_type)


async def _sync_intelligence_job() -> None:
    try:
        await sync_intelligence()
    except Exception as exc:
        _logger.error("intelligence_sync_failed", error=str(exc))


# ---------- 外部情报源拉取 ----------

async def _sync_external_intel() -> None:
    """从外部源拉取情报，写入 DB，再触发 DB→Redis 同步。"""
    from src.infrastructure.external_intel_fetcher import ExternalIntelFetcher
    try:
        async with Database.session() as session:
            repo = ThreatIntelRepository(session)
            fetcher = ExternalIntelFetcher()
            result = await fetcher.fetch_all()
            written = 0
            for entry in result:
                await repo.upsert(
                    ip=entry["ip"],
                    category=entry["category"],
                    severity=entry.get("severity", "medium"),
                    source=entry["source"],
                    confidence=entry.get("confidence", 80),
                    description=entry.get("description", ""),
                )
                written += 1
            await session.commit()
        _logger.info("external_intel_sync_done", written=written)
        # 同步完成后立即触发 DB→Redis 刷新
        await _sync_threat_intel()
    except Exception as exc:
        _logger.error("external_intel_sync_failed", error=str(exc))


# ---------- Clock 阈值 DB→Redis ----------

async def _resync_clock_limits() -> None:
    """把 DB 中全部 Clock 阈值重推 Redis，用于 Redis flush 后自愈。"""
    try:
        from src.application.services.clock_service import ClockService
        from src.infrastructure.clock_sync import ClockSync
        from src.infrastructure.repositories.clock_limits_repository import ClockLimitsRepository
        from fangyu_shared.redis_manager import RedisManager
        redis = RedisManager.get_client()
        sync = ClockSync(redis)
        async with Database.session() as session:
            repo = ClockLimitsRepository(session)
            rows = await repo.list_all()
        for row in rows:
            await sync.put_limits(ClockService._to_limits(row))
        _logger.info("clock_resync_done", count=len(rows))
    except Exception as exc:
        _logger.error("clock_resync_failed", error=str(exc))


# ---------- 规则缓存 DB→Redis ----------

async def _sync_rule_cache() -> None:
    """把所有站点的已发布规则全量重写入 Redis（many-to-many 分片）。"""
    try:
        from src.infrastructure.cache.rule_cache import RuleCache
        from src.infrastructure.repositories.rule_repository import RuleAdminRepository
        from fangyu_shared.schemas.rule import RuleStatus
        from fangyu_shared.redis_manager import RedisManager
        redis = RedisManager.get_client()
        cache = RuleCache(redis)
        async with Database.session() as session:
            repo = RuleAdminRepository(session)
            site_ids = await repo.list_site_ids_with_published_rules()
        for site_id in site_ids:
            async with Database.session() as session:
                repo = RuleAdminRepository(session)
                rules = await repo.list_published_by_site(site_id)
            await cache.replace_site(site_id, rules)
        _logger.info("rule_cache_sync_done", sites=len(site_ids))
    except Exception as exc:
        _logger.error("rule_cache_sync_failed", error=str(exc))


# ---------- 高风险声誉回流情报库（PROF→INTEL） ----------

async def _feedback_reputation_intel() -> None:
    """把离线画像算出的高风险 IP 沉淀成 ip_profile 情报条目。

    这里**不写 Redis ProfileCache**：那份周期回流由 worker 独占（数据面常驻
    进程）。此前 admin 也注册了完整的 reputation_sync 任务，两侧每小时各跑一次
    同样的聚合并各写一遍 Redis——纯粹的重复劳动，且两份实现一旦调参不一致，
    后跑的那次会把前一次的分数改掉。

    admin 在这条链路上唯一不可替代的部分是写 MySQL 情报库（worker 依赖里没有
    SQLAlchemy），故这个任务只保留该职责。
    """
    try:
        from fangyu_shared.clickhouse_manager import ClickHouseManager
        from fangyu_shared.reputation import fetch_ip_reputation

        from src.application.services.intel_service import IntelService
        from src.infrastructure.reputation_intel_feedback import (
            ReputationIntelFeedback,
            ReputationIntelFeedbackConfig,
        )

        cfg = ReputationIntelFeedbackConfig()
        if not cfg.enabled:
            return

        ch = ClickHouseManager.get_client()
        # lookback 与 min_samples 直接用情报回流自己的门槛：这里不需要
        # ProfileCache 那种低门槛（5 条样本）的行，取数时就按 200 过滤，
        # 让 ClickHouse 承担筛选而不是把百万行拉到进程里再丢掉。
        rows = await fetch_ip_reputation(ch, lookback_days=7, min_samples=cfg.min_samples)
        async with Database.session() as session:
            feedback = ReputationIntelFeedback(IntelService(session), cfg)
            written = await feedback.write(rows)
        _logger.info("reputation_intel_feedback_job_done", candidates=len(rows), written=written)
    except Exception as exc:
        _logger.error("reputation_intel_feedback_failed", error=str(exc))


# ---------- 调度器管理 ----------

def start_scheduler(
    sync_interval_seconds: int = 3600,
    external_intel_interval_seconds: int = 21600,
) -> AsyncIOScheduler:
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
    _scheduler.add_job(
        _sync_intelligence_job,
        trigger=IntervalTrigger(seconds=sync_interval_seconds),
        id="intelligence_sync",
        name="六类维度情报定期同步到 Redis",
        replace_existing=True,
        misfire_grace_time=60,
    )
    _scheduler.add_job(
        _sync_external_intel,
        trigger=IntervalTrigger(seconds=external_intel_interval_seconds),
        id="external_intel_sync",
        name="外部情报源定期拉取",
        replace_existing=True,
        misfire_grace_time=300,
    )
    _scheduler.add_job(
        _resync_clock_limits,
        trigger=IntervalTrigger(seconds=sync_interval_seconds),
        id="clock_resync",
        name="Clock 阈值定期同步到 Redis",
        replace_existing=True,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        _sync_rule_cache,
        trigger=IntervalTrigger(seconds=300),  # 每 5 分钟
        id="rule_cache_sync",
        name="已发布规则定期同步到 Redis",
        replace_existing=True,
        misfire_grace_time=60,
    )
    # 与外部情报拉取同频（默认 6 小时）而非每小时：情报条目是长期留存的结论，
    # 没有小时级刷新的必要，低频也顺带压低对 MV 的扫描次数。
    _scheduler.add_job(
        _feedback_reputation_intel,
        trigger=IntervalTrigger(seconds=external_intel_interval_seconds),
        id="reputation_intel_feedback",
        name="高风险声誉定期沉淀为 IP 画像情报",
        replace_existing=True,
        misfire_grace_time=300,
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

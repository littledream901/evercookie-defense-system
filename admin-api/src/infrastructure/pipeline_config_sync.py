"""流水线配置 Redis 同步器。

当 Admin API 更新流水线配置时，同步写入 Redis 缓存（fangyu:pipeline_config:site:{site_id}），
Gateway 侧 PipelineConfigCache 读取该缓存（TTL 30s）。
"""

from redis.asyncio import Redis

from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.pipeline import PipelineConfig

_logger = get_logger("admin.pipeline_config_sync")


class PipelineConfigSync:
    """流水线配置同步器：Admin API 更新配置后立即写入 Gateway 缓存。"""

    def __init__(self, redis: Redis, ttl: int = 30) -> None:
        self._redis = redis
        self._ttl = ttl

    def _key(self, site_id: int) -> str:
        return f"fangyu:pipeline_config:site:{site_id}"

    async def sync(self, site_id: int, config: PipelineConfig) -> None:
        """将配置写入 Redis，供 Gateway 读取。"""
        key = self._key(site_id)
        try:
            await self._redis.set(
                key,
                config.model_dump_json(),
                ex=self._ttl,
            )
            _logger.info(
                "pipeline_config_synced",
                extra={
                    "site_id": site_id,
                    "whitelist_enabled": config.whitelistEnabled,
                    "clock_enabled": config.clockEnabled,
                    "threat_intel_enabled": config.threatIntelEnabled,
                    "security_enabled": config.securityEnabled,
                    "rules_enabled": config.rulesEnabled,
                    "scoring_enabled": config.scoringEnabled,
                },
            )
        except Exception:
            _logger.exception(
                "pipeline_config_sync_failed",
                extra={"site_id": site_id, "key": key},
            )
            raise

    async def delete(self, site_id: int) -> None:
        """删除流水线配置缓存（站点删除时调用）。"""
        key = self._key(site_id)
        try:
            await self._redis.delete(key)
            _logger.info("pipeline_config_cache_deleted", extra={"site_id": site_id})
        except Exception:
            _logger.exception(
                "pipeline_config_cache_delete_failed",
                extra={"site_id": site_id, "key": key},
            )
            raise

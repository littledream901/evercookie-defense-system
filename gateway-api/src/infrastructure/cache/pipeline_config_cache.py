"""流水线配置缓存层。"""

from redis.asyncio import Redis

from fangyu_shared.schemas.pipeline import PipelineConfig


class PipelineConfigCache:
    """流水线配置缓存（TTL 30s）。"""

    def __init__(self, redis: Redis, ttl: int = 30) -> None:
        self._redis = redis
        self._ttl = ttl

    def _key(self, site_id: int) -> str:
        return f"fangyu:pipeline_config:site:{site_id}"

    async def get(self, site_id: int) -> PipelineConfig | None:
        """获取站点流水线配置（未命中返回 None）。"""
        raw = await self._redis.get(self._key(site_id))
        if raw is None:
            return None
        return PipelineConfig.model_validate_json(raw)

    async def set(self, site_id: int, config: PipelineConfig) -> None:
        """写入流水线配置缓存（Admin API 调用）。"""
        await self._redis.set(
            self._key(site_id),
            config.model_dump_json(),
            ex=self._ttl,
        )

    async def delete(self, site_id: int) -> None:
        """删除流水线配置缓存。"""
        await self._redis.delete(self._key(site_id))

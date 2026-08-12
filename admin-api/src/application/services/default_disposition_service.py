"""默认处置服务。"""

from __future__ import annotations

from fangyu_shared.logging import get_logger

from src.infrastructure.default_disposition_sync import DefaultDispositionSync
from src.infrastructure.repositories.default_disposition_repository import (
    DefaultDispositionRepository,
)
from src.infrastructure.repositories.models import DefaultDispositionModel

_logger = get_logger("admin.default_disposition_service")


class DefaultDispositionService:
    def __init__(
        self,
        repo: DefaultDispositionRepository,
        sync: DefaultDispositionSync,
    ) -> None:
        self._repo = repo
        self._sync = sync

    async def get(self, site_id: int) -> DefaultDispositionModel | None:
        return await self._repo.get_by_site(site_id)

    async def upsert(self, site_id: int, *, disposition: dict) -> DefaultDispositionModel:
        result = await self._repo.upsert(site_id, disposition=disposition)
        # 同步到 Redis，gateway 通过 RuleRepository 读取
        await self._sync.put(site_id, disposition=disposition)
        _logger.info("default_disposition_upserted", site_id=site_id)
        return result

    async def reset(self, site_id: int) -> bool:
        deleted = await self._repo.reset(site_id)
        if deleted:
            await self._sync.delete(site_id)
            _logger.info("default_disposition_reset", site_id=site_id)
        return deleted

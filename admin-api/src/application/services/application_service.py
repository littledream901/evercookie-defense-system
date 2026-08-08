"""应用管理服务（V3 两层架构）。

应用是站点的业务分组容器，本身不参与 gateway 验签，
因此无需同步 Redis —— 验签身份由其下的站点承载。
"""

from __future__ import annotations

import secrets

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.infrastructure.repositories.application_repository import ApplicationRepository
from src.infrastructure.repositories.models import ApplicationModel

_logger = get_logger("admin.application_service")


class ApplicationService:
    def __init__(self, app_repo: ApplicationRepository) -> None:
        self._repo = app_repo

    async def get(self, app_id: int) -> ApplicationModel:
        app = await self._repo.get(app_id)
        if app is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")
        return app

    async def list_paged(
        self,
        *,
        keyword: str | None = None,
        is_active: bool | None = None,
        owner_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ApplicationModel], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_paged(
            keyword=keyword,
            is_active=is_active,
            owner_id=owner_id,
            offset=offset,
            limit=page_size,
        )

    async def count_sites(self, app_id: int) -> int:
        return await self._repo.count_sites(app_id)

    async def get_names(self, app_ids: list[int]) -> dict[int, str]:
        return await self._repo.get_names(app_ids)

    async def count_sites_batch(self, app_ids: list[int]) -> dict[int, int]:
        return await self._repo.count_sites_batch(app_ids)

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        owner_user_id: int | None = None,
    ) -> tuple[ApplicationModel, str]:
        """创建应用，返回 (应用, 密钥明文)。密钥仅此一次可见。"""
        if not name:
            raise ValidationException("应用名不能为空")

        app_secret = _generate_app_secret()
        app = await self._repo.create(
            name=name,
            description=description or "",
            owner_user_id=owner_user_id,
            app_secret=app_secret,
        )
        _logger.info("application_created", app_id=app.id, name=name)
        return app, app_secret

    async def update(
        self,
        app_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> ApplicationModel:
        existing = await self._repo.get(app_id)
        if existing is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        updated = await self._repo.update(
            app_id,
            name=name,
            description=description,
            is_active=is_active,
        )
        if updated is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        _logger.info("application_updated", app_id=app_id)
        return updated

    async def rotate_secret(self, app_id: int) -> tuple[ApplicationModel, str]:
        """轮换应用密钥，返回 (应用, 新密钥明文)。"""
        existing = await self._repo.get(app_id)
        if existing is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        app_secret = _generate_app_secret()
        updated = await self._repo.rotate_secret(app_id, app_secret)
        if updated is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        _logger.info("application_secret_rotated", app_id=app_id)
        return updated, app_secret

    async def delete(self, app_id: int) -> None:
        app = await self._repo.get(app_id)
        if app is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        site_count = await self._repo.count_sites(app_id)
        if site_count > 0:
            raise BusinessRuleException(f"应用下仍有 {site_count} 个站点，需先删除站点")

        success = await self._repo.delete(app_id)
        if not success:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        _logger.info("application_deleted", app_id=app_id)


def _generate_app_secret() -> str:
    """应用级密钥：hex 格式 48 字符。"""
    return secrets.token_hex(24)


__all__ = ["ApplicationService"]

"""应用管理服务。"""

from __future__ import annotations

import secrets

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.domain.app.entities import Application, ApplicationStatus
from src.infrastructure.cache.app_key_sync import AppKeyRedisSync
from src.infrastructure.repositories.app_repository import AppRepository

_logger = get_logger("admin.app_service")


class AppService:
    def __init__(
        self,
        app_repo: AppRepository,
        *,
        app_key_sync: AppKeyRedisSync | None = None,
    ) -> None:
        self._repo = app_repo
        self._app_key_sync = app_key_sync

    async def list_paged(
        self,
        *,
        keyword: str | None,
        status: ApplicationStatus | None,
        owner_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Application], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._repo.list_paged(
            keyword=keyword,
            status=status,
            owner_id=owner_id,
            offset=offset,
            limit=page_size,
        )

    async def list_by_owner(self, owner_id: int) -> list[Application]:
        return await self._repo.list_by_owner(owner_id)

    async def get(self, app_id: int) -> Application:
        app = await self._repo.get(app_id)
        if app is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")
        return app

    async def create(
        self,
        *,
        name: str,
        owner_user_id: int,
        description: str = "",
        domains: list[str] | None = None,
    ) -> Application:
        if not name:
            raise ValidationException("应用名不能为空")
        app = Application(
            id=None,
            name=name,
            api_key=self._generate_api_key(),
            owner_user_id=owner_user_id,
            status=ApplicationStatus.ACTIVE,
            description=description,
            domains=list(domains or []),
        )
        created = await self._repo.create(app)
        await self._sync_bind(created)
        _logger.info("app_created", app_id=created.id, owner=owner_user_id)
        return created

    async def update(
        self,
        app_id: int,
        *,
        name: str | None,
        description: str | None,
        domains: list[str] | None,
        status: ApplicationStatus | None,
    ) -> Application:
        existing = await self._repo.get(app_id)
        if existing is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        # 先在调用 repo 之前把 archive 判定需要的字段快照下来，避免 ORM 会话
        # 内的对象引用被覆盖。
        previous_status = existing.status
        previous_api_key = existing.api_key

        updated = await self._repo.update(
            app_id,
            name=name,
            description=description,
            domains=domains,
            status=status,
        )
        if updated is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        # 归档时立刻回收 Redis 中的 API Key 映射，避免继续被使用。
        if (
            previous_status != ApplicationStatus.ARCHIVED
            and updated.status == ApplicationStatus.ARCHIVED
        ):
            await self._sync_unbind(previous_api_key)

        _logger.info("app_updated", app_id=app_id)
        return updated

    async def rotate_api_key(self, app_id: int) -> Application:
        existing = await self._repo.get(app_id)
        if existing is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        # 先快照旧 key，避免 repo 内部原地改写 existing.api_key 后无法回收。
        previous_api_key = existing.api_key

        new_key = self._generate_api_key()
        updated = await self._repo.rotate_api_key(app_id, new_key)
        if updated is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        await self._sync_rebind(previous_api_key, updated.api_key, updated.id or app_id)
        _logger.info("app_api_key_rotated", app_id=app_id)
        return updated

    async def delete(self, app_id: int) -> None:
        app = await self._repo.get(app_id)
        if app is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")
        if app.status == ApplicationStatus.ACTIVE:
            raise BusinessRuleException("激活状态的应用需先暂停后再删除")
        await self._repo.delete(app_id)
        await self._sync_unbind(app.api_key)
        _logger.info("app_deleted", app_id=app_id)

    async def _sync_bind(self, app: Application) -> None:
        if self._app_key_sync is None or app.id is None:
            return
        await self._app_key_sync.bind(app.api_key, app.id)

    async def _sync_unbind(self, api_key: str) -> None:
        if self._app_key_sync is None:
            return
        await self._app_key_sync.unbind(api_key)

    async def _sync_rebind(self, old_key: str, new_key: str, app_id: int) -> None:
        if self._app_key_sync is None:
            return
        await self._app_key_sync.rebind(old_key, new_key, app_id)

    @staticmethod
    def _generate_api_key() -> str:
        return f"fangyu_{secrets.token_urlsafe(32)}"

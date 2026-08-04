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
        status: str | None,
        owner_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Application], int]:
        offset = max(0, (page - 1) * page_size)
        is_active: bool | None = None
        if status == "active":
            is_active = True
        elif status in ("paused", "inactive"):
            is_active = False
        return await self._repo.list_paged(
            keyword=keyword,
            is_active=is_active,
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
        domain: str,
        alt_domains: list[str] | None = None,
        access_mode: str = "adapter",
        sdk_version: str | None = None,
        gateway_url: str | None = None,
        clock_stats_enabled: bool = True,
        log_retention_days: int = 30,
        remark: str | None = None,
    ) -> Application:
        if not name:
            raise ValidationException("应用名不能为空")
        app_secret = self._generate_app_secret()
        app = Application(
            id=None,
            site_id="",          # 由 Repository._gen_site_id() 生成
            name=name,
            domain=domain,
            app_secret=app_secret,
            owner_user_id=owner_user_id,
            alt_domains=list(alt_domains or []),
            access_mode=access_mode,
            sdk_version=sdk_version,
            gateway_url=gateway_url,
            clock_stats_enabled=clock_stats_enabled,
            log_retention_days=log_retention_days,
            remark=remark,
        )
        created = await self._repo.create(app)
        created.app_secret = app_secret
        await self._sync_bind(created)
        _logger.info("app_created", app_id=created.id, owner=owner_user_id)
        return created

    async def update(
        self,
        app_id: int,
        *,
        name: str | None,
        alt_domains: list[str] | None,
        access_mode: str | None,
        sdk_version: str | None,
        gateway_url: str | None,
        is_active: bool | None,
        clock_stats_enabled: bool | None,
        log_retention_days: int | None,
        remark: str | None,
    ) -> Application:
        existing = await self._repo.get(app_id)
        if existing is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        updated = await self._repo.update(
            app_id,
            name=name,
            alt_domains=alt_domains,
            access_mode=access_mode,
            sdk_version=sdk_version,
            gateway_url=gateway_url,
            is_active=is_active,
            clock_stats_enabled=clock_stats_enabled,
            log_retention_days=log_retention_days,
            remark=remark,
        )
        if updated is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        if is_active is False:
            await self._sync_unbind(existing.site_id, app_id)
        elif is_active is True:
            await self._sync_bind(updated)

        _logger.info("app_updated", app_id=app_id)
        return updated

    async def rotate_api_key(self, app_id: int) -> Application:
        existing = await self._repo.get(app_id)
        if existing is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        app_secret = self._generate_app_secret()
        updated = await self._repo.rotate_secret(app_id, app_secret)
        if updated is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")

        # site_id 不变，只需更新 Redis 里的 app_secret
        await self._sync_bind(updated, secret=app_secret)
        updated.app_secret = app_secret
        _logger.info("app_secret_rotated", app_id=app_id)
        return updated

    async def delete(self, app_id: int) -> None:
        app = await self._repo.get(app_id)
        if app is None:
            raise ResourceNotFoundException(f"应用不存在: {app_id}")
        if app.status == ApplicationStatus.ACTIVE:
            raise BusinessRuleException("激活状态的应用需先暂停后再删除")
        await self._repo.delete(app_id)
        await self._sync_unbind(app.site_id, app_id)
        _logger.info("app_deleted", app_id=app_id)

    async def batch_delete(self, app_ids: list[int]) -> tuple[list[int], list[dict[str, str]]]:
        """逐条删除，单条失败不影响其他项。返回 (成功 id 列表, 失败明细)。"""
        succeeded: list[int] = []
        failed: list[dict[str, str]] = []
        for app_id in app_ids:
            try:
                await self.delete(app_id)
                succeeded.append(app_id)
            except (ResourceNotFoundException, BusinessRuleException) as exc:
                failed.append({"id": str(app_id), "reason": str(exc)})
        _logger.info("app_batch_deleted", succeeded=len(succeeded), failed=len(failed))
        return succeeded, failed

    async def batch_set_active(
        self, app_ids: list[int], *, is_active: bool
    ) -> tuple[list[int], list[dict[str, str]]]:
        """批量启用 / 停用；同步 Redis 绑定。"""
        succeeded: list[int] = []
        failed: list[dict[str, str]] = []
        for app_id in app_ids:
            try:
                await self.update(
                    app_id,
                    name=None,
                    alt_domains=None,
                    access_mode=None,
                    sdk_version=None,
                    gateway_url=None,
                    is_active=is_active,
                    clock_stats_enabled=None,
                    log_retention_days=None,
                    remark=None,
                )
                succeeded.append(app_id)
            except (ResourceNotFoundException, BusinessRuleException) as exc:
                failed.append({"id": str(app_id), "reason": str(exc)})
        _logger.info(
            "app_batch_set_active",
            is_active=is_active,
            succeeded=len(succeeded),
            failed=len(failed),
        )
        return succeeded, failed

    async def batch_update(
        self,
        app_ids: list[int],
        *,
        access_mode: str | None = None,
        clock_stats_enabled: bool | None = None,
        log_retention_days: int | None = None,
    ) -> tuple[list[int], list[dict[str, str]]]:
        """批量修改通用配置；未传字段保持原值。"""
        succeeded: list[int] = []
        failed: list[dict[str, str]] = []
        for app_id in app_ids:
            try:
                await self.update(
                    app_id,
                    name=None,
                    alt_domains=None,
                    access_mode=access_mode,
                    sdk_version=None,
                    gateway_url=None,
                    is_active=None,
                    clock_stats_enabled=clock_stats_enabled,
                    log_retention_days=log_retention_days,
                    remark=None,
                )
                succeeded.append(app_id)
            except (ResourceNotFoundException, BusinessRuleException) as exc:
                failed.append({"id": str(app_id), "reason": str(exc)})
        _logger.info("app_batch_updated", succeeded=len(succeeded), failed=len(failed))
        return succeeded, failed

    async def _sync_bind(self, app: Application, *, secret: str | None = None) -> None:
        if self._app_key_sync is None or app.id is None:
            return
        effective_secret = secret or app.app_secret
        await self._app_key_sync.bind(app.site_id, app.id, effective_secret)

    async def _sync_unbind(self, site_id: str, app_id: int | None = None) -> None:
        """解绑 Redis 映射。

        传 ``app_id`` 时会连带清理 ``fangyu:app_secrets:{app_id}`` 反向索引——
        仅用于删除/停用，密钥轮换走 ``_sync_bind`` 覆盖写，不能清索引。
        """
        if self._app_key_sync is None:
            return
        await self._app_key_sync.unbind(site_id, app_id)

    @staticmethod
    def _generate_app_secret() -> str:
        """验签密钥：使用 hex 格式，与 site_id 格式明显区分，不易混用。"""
        return secrets.token_hex(24)

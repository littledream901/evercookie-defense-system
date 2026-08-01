"""用户管理服务。"""

from __future__ import annotations

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.domain.user.entities import User, UserStatus
from src.domain.user.password import PasswordService
from src.infrastructure.cache.permission_cache import PermissionCache
from src.infrastructure.repositories.rbac_repository import RbacRepository
from src.infrastructure.repositories.user_repository import UserRepository

_logger = get_logger("admin.user_service")


class UserService:
    def __init__(
        self,
        *,
        user_repo: UserRepository,
        rbac_repo: RbacRepository,
        password_service: PasswordService,
        permission_cache: PermissionCache,
    ) -> None:
        self._user_repo = user_repo
        self._rbac_repo = rbac_repo
        self._password_service = password_service
        self._permission_cache = permission_cache

    async def list_users(
        self,
        *,
        keyword: str | None,
        status: UserStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[User], int]:
        offset = max(0, (page - 1) * page_size)
        return await self._user_repo.list_paged(
            keyword=keyword, status=status, offset=offset, limit=page_size
        )

    async def get_user(self, user_id: int) -> User:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException(f"用户不存在: {user_id}")
        return user

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        display_name: str,
        role_ids: list[int],
    ) -> User:
        if await self._user_repo.get_by_username(username) is not None:
            raise BusinessRuleException(f"用户名已存在: {username}")
        password_hash = self._password_service.hash(password)
        await self._ensure_roles_exist(role_ids)

        created = await self._user_repo.create(
            User(
                id=None,
                username=username,
                email=email,
                password_hash=password_hash,
                display_name=display_name,
                status=UserStatus.ACTIVE,
            )
        )
        assert created.id is not None
        if role_ids:
            await self._user_repo.replace_roles(created.id, role_ids)
        _logger.info("user_created", user_id=created.id, username=username)
        return await self.get_user(created.id)

    async def update_profile(
        self,
        user_id: int,
        *,
        email: str | None = None,
        display_name: str | None = None,
        status: UserStatus | None = None,
    ) -> User:
        updated = await self._user_repo.update_profile(
            user_id, email=email, display_name=display_name, status=status
        )
        if updated is None:
            raise ResourceNotFoundException(f"用户不存在: {user_id}")
        await self._permission_cache.invalidate(user_id)
        _logger.info("user_updated", user_id=user_id)
        return updated

    async def reset_password(self, user_id: int, new_password: str) -> None:
        if not new_password or len(new_password) < 8:
            raise ValidationException("密码长度不能少于 8 位")
        password_hash = self._password_service.hash(new_password)
        ok = await self._user_repo.update_password(user_id, password_hash)
        if not ok:
            raise ResourceNotFoundException(f"用户不存在: {user_id}")
        await self._permission_cache.invalidate(user_id)
        _logger.info("user_password_reset", user_id=user_id)

    async def assign_roles(self, user_id: int, role_ids: list[int]) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundException(f"用户不存在: {user_id}")
        await self._ensure_roles_exist(role_ids)
        await self._user_repo.replace_roles(user_id, role_ids)
        await self._permission_cache.invalidate(user_id)
        _logger.info("user_roles_assigned", user_id=user_id, role_ids=role_ids)

    async def delete_user(self, user_id: int) -> None:
        ok = await self._user_repo.delete(user_id)
        if not ok:
            raise ResourceNotFoundException(f"用户不存在: {user_id}")
        await self._permission_cache.invalidate(user_id)
        _logger.info("user_deleted", user_id=user_id)

    async def _ensure_roles_exist(self, role_ids: list[int]) -> None:
        for rid in set(role_ids):
            if await self._rbac_repo.get_role(rid) is None:
                raise ValidationException(f"角色不存在: {rid}")

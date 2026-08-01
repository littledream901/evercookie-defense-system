"""角色与权限管理服务。"""

from __future__ import annotations

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.domain.rbac.entities import Permission, Role
from src.infrastructure.cache.permission_cache import PermissionCache
from src.infrastructure.repositories.rbac_repository import RbacRepository

_logger = get_logger("admin.role_service")


def _validate_permission_code(code: str) -> None:
    if not code or "." not in code:
        raise ValidationException(f"权限码需为 resource.action 形式: {code}")


class RoleService:
    def __init__(
        self,
        *,
        rbac_repo: RbacRepository,
        permission_cache: PermissionCache,
    ) -> None:
        self._repo = rbac_repo
        self._perm_cache = permission_cache

    # ---------- 角色 ----------
    async def list_roles(self) -> list[Role]:
        return await self._repo.list_roles()

    async def get_role(self, role_id: int) -> Role:
        role = await self._repo.get_role(role_id)
        if role is None:
            raise ResourceNotFoundException(f"角色不存在: {role_id}")
        return role

    async def create_role(
        self,
        *,
        name: str,
        description: str,
        permissions: list[str],
    ) -> Role:
        if await self._repo.get_role_by_name(name) is not None:
            raise BusinessRuleException(f"角色名已存在: {name}")
        for code in permissions:
            _validate_permission_code(code)
        role = await self._repo.create_role(
            name=name,
            description=description,
            is_system=False,
            permissions=permissions,
        )
        _logger.info("role_created", role_id=role.id, name=name)
        return role

    async def update_role(
        self,
        role_id: int,
        *,
        description: str | None,
        permissions: list[str] | None,
    ) -> Role:
        current = await self._repo.get_role(role_id)
        if current is None:
            raise ResourceNotFoundException(f"角色不存在: {role_id}")
        if current.is_system and permissions is not None:
            raise BusinessRuleException("系统角色不允许修改权限")
        if permissions is not None:
            for code in permissions:
                _validate_permission_code(code)
        updated = await self._repo.update_role(
            role_id, description=description, permissions=permissions
        )
        if updated is None:
            raise ResourceNotFoundException(f"角色不存在: {role_id}")
        _logger.info("role_updated", role_id=role_id)
        return updated

    async def delete_role(self, role_id: int) -> None:
        current = await self._repo.get_role(role_id)
        if current is None:
            raise ResourceNotFoundException(f"角色不存在: {role_id}")
        if current.is_system:
            raise BusinessRuleException("系统角色不可删除")
        ok = await self._repo.delete_role(role_id)
        if not ok:
            raise BusinessRuleException("角色删除失败")
        _logger.info("role_deleted", role_id=role_id)

    # ---------- 权限 ----------
    async def list_permissions(self) -> list[Permission]:
        return await self._repo.list_permissions()

    async def upsert_permission(self, code: str, description: str) -> Permission:
        _validate_permission_code(code)
        perm = await self._repo.upsert_permission(code, description)
        _logger.info("permission_upserted", code=code)
        return perm

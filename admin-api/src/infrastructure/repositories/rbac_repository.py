"""RBAC 仓储：角色 + 权限 + 关联表管理。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.rbac.entities import Permission, Role
from src.infrastructure.repositories.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)


class RbacRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------- 角色查询 ----------
    async def get_user_roles(self, user_id: int) -> list[Role]:
        stmt = (
            select(RoleModel)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
            .where(UserRoleModel.user_id == user_id)
            .options(selectinload(RoleModel.permissions))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._role_to_domain(r) for r in rows]

    async def list_roles(self) -> list[Role]:
        stmt = select(RoleModel).options(selectinload(RoleModel.permissions))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._role_to_domain(r) for r in rows]

    async def get_role(self, role_id: int) -> Role | None:
        stmt = (
            select(RoleModel)
            .where(RoleModel.id == role_id)
            .options(selectinload(RoleModel.permissions))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._role_to_domain(row) if row else None

    async def get_role_by_name(self, name: str) -> Role | None:
        stmt = (
            select(RoleModel)
            .where(RoleModel.name == name)
            .options(selectinload(RoleModel.permissions))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._role_to_domain(row) if row else None

    # ---------- 角色写入 ----------
    async def create_role(
        self,
        *,
        name: str,
        description: str,
        is_system: bool,
        permissions: list[str],
    ) -> Role:
        model = RoleModel(name=name, description=description, is_system=is_system)
        self._session.add(model)
        await self._session.flush()
        await self._sync_role_permissions(model.id, permissions)
        return await self.get_role(model.id) or self._role_to_domain(model)

    async def update_role(
        self,
        role_id: int,
        *,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> Role | None:
        model = await self._session.get(RoleModel, role_id)
        if model is None:
            return None
        if description is not None:
            model.description = description
        if permissions is not None:
            await self._sync_role_permissions(role_id, permissions)
        await self._session.flush()
        return await self.get_role(role_id)

    async def delete_role(self, role_id: int) -> bool:
        model = await self._session.get(RoleModel, role_id)
        if model is None or model.is_system:
            return False
        await self._session.execute(
            delete(UserRoleModel).where(UserRoleModel.role_id == role_id)
        )
        await self._session.execute(
            delete(RolePermissionModel).where(RolePermissionModel.role_id == role_id)
        )
        await self._session.delete(model)
        await self._session.flush()
        return True

    # ---------- 权限查询 ----------
    async def list_permissions(self) -> list[Permission]:
        stmt = select(PermissionModel).order_by(PermissionModel.code)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [Permission(code=r.code, description=r.description) for r in rows]

    async def upsert_permission(self, code: str, description: str) -> Permission:
        stmt = select(PermissionModel).where(PermissionModel.code == code).limit(1)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = PermissionModel(code=code, description=description)
            self._session.add(row)
        else:
            row.description = description
        await self._session.flush()
        return Permission(code=row.code, description=row.description)

    # ---------- 内部工具 ----------
    async def _sync_role_permissions(self, role_id: int, permissions: list[str]) -> None:
        await self._session.execute(
            delete(RolePermissionModel).where(RolePermissionModel.role_id == role_id)
        )
        for code in set(permissions):
            self._session.add(
                RolePermissionModel(role_id=role_id, permission_code=code)
            )
        await self._session.flush()

    @staticmethod
    def _role_to_domain(row: RoleModel | None) -> Role | None:
        if row is None:
            return None
        perms = frozenset(p.permission_code for p in (row.permissions or []))
        return Role(
            id=row.id,
            name=row.name,
            description=row.description,
            is_system=row.is_system,
            permissions=perms,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

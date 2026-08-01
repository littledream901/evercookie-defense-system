"""用户仓储。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.user.entities import User, UserStatus
from src.infrastructure.repositories.models import UserModel, UserRoleModel


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(UserModel).where(UserModel.username == username).limit(1)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_id(self, user_id: int) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return self._to_domain(row) if row else None

    async def list_paged(
        self,
        *,
        keyword: str | None = None,
        status: UserStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[User], int]:
        base = select(UserModel)
        if keyword:
            like = f"%{keyword}%"
            base = base.where(
                (UserModel.username.ilike(like))
                | (UserModel.email.ilike(like))
                | (UserModel.display_name.ilike(like))
            )
        if status is not None:
            base = base.where(UserModel.status == status.value)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = base.order_by(UserModel.id.desc()).offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        items = [self._to_domain(r) for r in rows if r is not None]
        return [u for u in items if u is not None], int(total)

    async def create(self, user: User) -> User:
        model = UserModel(
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            password_hash=user.password_hash,
            status=user.status.value,
            must_change_password=user.must_change_password,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)  # type: ignore[return-value]

    async def update_profile(
        self,
        user_id: int,
        *,
        email: str | None = None,
        display_name: str | None = None,
        status: UserStatus | None = None,
    ) -> User | None:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            return None
        if email is not None:
            model.email = email
        if display_name is not None:
            model.display_name = display_name
        if status is not None:
            model.status = status.value
        await self._session.flush()
        return self._to_domain(model)

    async def update_password(self, user_id: int, password_hash: str) -> bool:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            return False
        model.password_hash = password_hash
        model.must_change_password = False
        await self._session.flush()
        return True

    async def delete(self, user_id: int) -> bool:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            return False
        await self._session.execute(
            delete(UserRoleModel).where(UserRoleModel.user_id == user_id)
        )
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def update_last_login(self, user_id: int, at: str | None = None) -> None:
        user = await self._session.get(UserModel, user_id)
        if user is None:
            return
        user.last_login_at = datetime.utcnow() if at is None else datetime.fromisoformat(at)

    async def get_role_ids(self, user_id: int) -> list[int]:
        stmt = select(UserRoleModel.role_id).where(UserRoleModel.user_id == user_id)
        return [int(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def replace_roles(self, user_id: int, role_ids: list[int]) -> None:
        await self._session.execute(
            delete(UserRoleModel).where(UserRoleModel.user_id == user_id)
        )
        for rid in set(role_ids):
            self._session.add(UserRoleModel(user_id=user_id, role_id=rid))
        await self._session.flush()

    @staticmethod
    def _to_domain(row: UserModel | None) -> User | None:
        if row is None:
            return None
        return User(
            id=row.id,
            username=row.username,
            email=row.email,
            password_hash=row.password_hash,
            display_name=row.display_name,
            status=UserStatus(row.status),
            must_change_password=row.must_change_password,
            role_ids=[ur.role_id for ur in (row.roles or [])],
            last_login_at=row.last_login_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

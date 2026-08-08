"""用户 API Key 数据访问层。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.models import UserApiKeyModel


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        name: str,
        key_prefix: str,
        key_hash: str,
    ) -> UserApiKeyModel:
        model = UserApiKeyModel(
            user_id=user_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            status="active",
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def list_by_user(self, user_id: int) -> list[UserApiKeyModel]:
        stmt = select(UserApiKeyModel).where(UserApiKeyModel.user_id == user_id).order_by(UserApiKeyModel.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, key_id: int) -> UserApiKeyModel | None:
        stmt = select(UserApiKeyModel).where(UserApiKeyModel.id == key_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_key_hash(self, key_hash: str) -> UserApiKeyModel | None:
        stmt = select(UserApiKeyModel).where(UserApiKeyModel.key_hash == key_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, key_id: int) -> bool:
        model = await self.get_by_id(key_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def update_last_used(self, key_id: int) -> None:
        stmt = select(UserApiKeyModel).where(UserApiKeyModel.id == key_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            from fangyu_shared.utils.time import utcnow
            model.last_used_at = utcnow()
            await self._session.flush()

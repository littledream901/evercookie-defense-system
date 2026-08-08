"""用户 API Key 管理服务。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fangyu_shared.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.infrastructure.repositories.api_key_repository import ApiKeyRepository
from src.infrastructure.repositories.models import UserApiKeyModel

_logger = get_logger("admin.api_key_service")


class ApiKeyService:
    def __init__(self, *, api_key_repo: ApiKeyRepository) -> None:
        self._api_key_repo = api_key_repo

    @staticmethod
    def _generate_api_key() -> tuple[str, str, str]:
        """生成 API Key。
        
        Returns:
            (完整key, key_prefix, key_hash)
        """
        random_key = secrets.token_urlsafe(32)
        api_key = f"fy_{random_key}"
        key_prefix = api_key[:12]
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return api_key, key_prefix, key_hash

    async def create_api_key(
        self,
        *,
        user_id: int,
        name: str,
    ) -> tuple[UserApiKeyModel, str]:
        """创建 API Key。
        
        Args:
            user_id: 用户 ID
            name: Key 名称
            
        Returns:
            (model, 完整的 API Key)
        """
        if not name or len(name.strip()) == 0:
            raise ValidationException("API Key 名称不能为空")
        
        if len(name) > 128:
            raise ValidationException("API Key 名称不能超过 128 字符")

        api_key, key_prefix, key_hash = self._generate_api_key()
        
        model = await self._api_key_repo.create(
            user_id=user_id,
            name=name.strip(),
            key_prefix=key_prefix,
            key_hash=key_hash,
        )
        
        _logger.info(f"用户 {user_id} 创建了 API Key: {model.id}")
        return model, api_key

    async def list_user_keys(self, user_id: int) -> list[UserApiKeyModel]:
        """列出用户的所有 API Key。"""
        return await self._api_key_repo.list_by_user(user_id)

    async def delete_api_key(self, *, key_id: int, user_id: int) -> None:
        """删除 API Key。
        
        Args:
            key_id: Key ID
            user_id: 用户 ID（用于权限校验）
        """
        model = await self._api_key_repo.get_by_id(key_id)
        if model is None:
            raise ResourceNotFoundException(f"API Key {key_id} 不存在")
        
        if model.user_id != user_id:
            raise BusinessRuleException("无权删除此 API Key")
        
        await self._api_key_repo.delete(key_id)
        _logger.info(f"用户 {user_id} 删除了 API Key: {key_id}")

    async def verify_api_key(self, api_key: str) -> UserApiKeyModel | None:
        """验证 API Key 是否有效。
        
        Args:
            api_key: 完整的 API Key
            
        Returns:
            如果有效返回 model，否则返回 None
        """
        if not api_key or not api_key.startswith("fy_"):
            return None
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        model = await self._api_key_repo.get_by_key_hash(key_hash)
        
        if model is None or model.status != "active":
            return None
        
        await self._api_key_repo.update_last_used(model.id)
        return model

"""认证与鉴权服务。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta

import jwt

from fangyu_shared.exceptions import (
    AuthenticationException,
    PermissionDeniedException,
    ValidationException,
)
from fangyu_shared.logging import get_logger

from src.config import AdminSettings
from src.domain.rbac.policy import PermissionContext, PermissionPolicy
from src.domain.user.entities import User, UserStatus
from src.domain.user.password import PasswordService
from src.infrastructure.cache.permission_cache import PermissionCache
from src.infrastructure.repositories.rbac_repository import RbacRepository
from src.infrastructure.repositories.user_repository import UserRepository

_logger = get_logger("admin.auth_service")


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    tokens: TokenPair
    permissions: PermissionContext
    password_change_required: bool = False


class AuthService:
    def __init__(
        self,
        *,
        user_repo: UserRepository,
        rbac_repo: RbacRepository,
        permission_cache: PermissionCache,
        password_service: PasswordService,
        settings: AdminSettings,
    ) -> None:
        self._user_repo = user_repo
        self._rbac_repo = rbac_repo
        self._permission_cache = permission_cache
        self._password_service = password_service
        self._settings = settings

    async def login(self, username: str, password: str) -> LoginResult:
        user = await self._user_repo.get_by_username(username)
        if user is None or not user.is_active:
            raise AuthenticationException("用户名或密码错误")
        if not self._password_service.verify(password, user.password_hash):
            raise AuthenticationException("用户名或密码错误")

        assert user.id is not None
        await self._user_repo.update_last_login(user.id)
        permissions = await self._load_permissions(user.id, force=True)
        tokens = self._issue_tokens(user.id)

        _logger.info("user_login_success", user_id=user.id, username=username)
        return LoginResult(
            user=user,
            tokens=tokens,
            permissions=permissions,
            password_change_required=user.must_change_password,
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = self._decode_token(refresh_token, expected_type="refresh")
        user_id = int(payload["sub"])
        user = await self._user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationException("用户不存在或已停用")
        tokens = self._issue_tokens(user_id)
        _logger.info("user_token_refreshed", user_id=user_id)
        return tokens

    async def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        if new_password == old_password:
            raise ValidationException("新密码不能与旧密码相同")
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise AuthenticationException("用户不存在")
        if not self._password_service.verify(old_password, user.password_hash):
            raise AuthenticationException("旧密码不正确")
        new_hash = self._password_service.hash(new_password)
        await self._user_repo.update_password(user_id, new_hash)
        await self._permission_cache.invalidate(user_id)
        _logger.info("user_password_changed", user_id=user_id)

    async def verify_token(self, token: str) -> int:
        payload = self._decode_token(token, expected_type="access")
        return int(payload["sub"])

    async def check_permission(self, user_id: int, code: str) -> None:
        ctx = await self._load_permissions(user_id)
        if not ctx.has(code):
            raise PermissionDeniedException(
                f"缺少权限: {code}",
                details={"required": code},
            )

    async def get_permission_context(self, user_id: int) -> PermissionContext:
        return await self._load_permissions(user_id)

    async def invalidate_permission_cache(self, user_id: int) -> None:
        await self._permission_cache.invalidate(user_id)

    def _decode_token(self, token: str, *, expected_type: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationException("Token 无效") from exc
        if payload.get("type") != expected_type:
            raise AuthenticationException("Token 类型不匹配")
        exp = int(payload.get("exp") or 0)
        if exp < int(time.time()):
            raise AuthenticationException("Token 已过期")
        if "sub" not in payload:
            raise AuthenticationException("Token 缺少主体")
        return payload

    async def _load_permissions(self, user_id: int, *, force: bool = False) -> PermissionContext:
        if not force:
            cached = await self._permission_cache.get(user_id)
            if cached is not None:
                return cached
        roles = await self._rbac_repo.get_user_roles(user_id)
        ctx = PermissionPolicy.build_context(user_id, roles)
        await self._permission_cache.set(ctx)
        return ctx

    def _issue_tokens(self, user_id: int) -> TokenPair:
        now_ts = int(time.time())
        access_exp = now_ts + self._settings.jwt_ttl_seconds
        refresh_exp = now_ts + self._settings.jwt_refresh_ttl_seconds
        access_token = jwt.encode(
            {"sub": str(user_id), "exp": access_exp, "type": "access"},
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )
        refresh_token = jwt.encode(
            {"sub": str(user_id), "exp": refresh_exp, "type": "refresh"},
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._settings.jwt_ttl_seconds,
        )

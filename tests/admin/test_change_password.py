"""首登改密 + 密码强度单元测试。"""
from __future__ import annotations

import pytest

from fangyu_shared.exceptions import AuthenticationException, ValidationException

from src.application.services.auth_service import AuthService
from src.domain.user.entities import User, UserStatus
from src.domain.user.password import PasswordService as RealPasswordService


class _StubPasswordService:
    """简化的密码服务，避免 bcrypt 依赖。"""

    def hash(self, password: str) -> str:
        RealPasswordService.validate_strength(password)
        return f"hashed_{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed_{password}"


class _StubUserRepo:
    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.next_id = 1

    async def get_by_username(self, username: str) -> User | None:
        for u in self.users.values():
            if u.username == username:
                return u
        return None

    async def get_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    async def update_last_login(self, user_id: int, at: str | None = None) -> None:
        pass

    async def update_password(self, user_id: int, password_hash: str) -> bool:
        user = self.users.get(user_id)
        if user is None:
            return False
        user.password_hash = password_hash
        user.must_change_password = False
        return True


class _StubRbacRepo:
    async def get_user_roles(self, user_id: int) -> list:
        return []


class _StubPermissionCache:
    async def get(self, user_id: int):
        return None

    async def set(self, ctx):
        pass

    async def invalidate(self, user_id: int):
        pass


class _StubSettings:
    jwt_secret = "test_secret"
    jwt_algorithm = "HS256"
    jwt_ttl_seconds = 7200
    jwt_refresh_ttl_seconds = 604800


def test_password_strength_validation_success():
    RealPasswordService.validate_strength("Abcd1234")


def test_password_strength_validation_too_short():
    with pytest.raises(ValueError, match="密码长度不能少于 8 位"):
        RealPasswordService.validate_strength("Abc123")


def test_password_strength_validation_no_lowercase():
    with pytest.raises(ValueError, match="密码必须包含小写字母"):
        RealPasswordService.validate_strength("ABCD1234")


def test_password_strength_validation_no_uppercase():
    with pytest.raises(ValueError, match="密码必须包含大写字母"):
        RealPasswordService.validate_strength("abcd1234")


def test_password_strength_validation_no_digit():
    with pytest.raises(ValueError, match="密码必须包含数字"):
        RealPasswordService.validate_strength("AbcdEfgh")


@pytest.mark.asyncio
async def test_login_returns_password_change_required():
    user_repo = _StubUserRepo()
    ps = _StubPasswordService()
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        password_hash=ps.hash("Abcd1234"),
        status=UserStatus.ACTIVE,
        must_change_password=True,
    )
    user_repo.users[1] = user

    auth_service = AuthService(
        user_repo=user_repo,  # type: ignore[arg-type]
        rbac_repo=_StubRbacRepo(),  # type: ignore[arg-type]
        permission_cache=_StubPermissionCache(),  # type: ignore[arg-type]
        password_service=ps,  # type: ignore[arg-type]
        settings=_StubSettings(),  # type: ignore[arg-type]
    )

    result = await auth_service.login("testuser", "Abcd1234")
    assert result.password_change_required is True


@pytest.mark.asyncio
async def test_change_password_sets_flag_to_false():
    user_repo = _StubUserRepo()
    ps = _StubPasswordService()
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        password_hash=ps.hash("OldPass1"),
        status=UserStatus.ACTIVE,
        must_change_password=True,
    )
    user_repo.users[1] = user

    auth_service = AuthService(
        user_repo=user_repo,  # type: ignore[arg-type]
        rbac_repo=_StubRbacRepo(),  # type: ignore[arg-type]
        permission_cache=_StubPermissionCache(),  # type: ignore[arg-type]
        password_service=ps,  # type: ignore[arg-type]
        settings=_StubSettings(),  # type: ignore[arg-type]
    )

    await auth_service.change_password(1, "OldPass1", "NewPass2")
    
    updated_user = user_repo.users[1]
    assert updated_user.must_change_password is False


@pytest.mark.asyncio
async def test_change_password_rejects_weak_password():
    user_repo = _StubUserRepo()
    ps = _StubPasswordService()
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        password_hash=ps.hash("OldPass1"),
        status=UserStatus.ACTIVE,
    )
    user_repo.users[1] = user

    auth_service = AuthService(
        user_repo=user_repo,  # type: ignore[arg-type]
        rbac_repo=_StubRbacRepo(),  # type: ignore[arg-type]
        permission_cache=_StubPermissionCache(),  # type: ignore[arg-type]
        password_service=ps,  # type: ignore[arg-type]
        settings=_StubSettings(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="密码必须包含大写字母"):
        await auth_service.change_password(1, "OldPass1", "newpass2")


@pytest.mark.asyncio
async def test_change_password_rejects_same_password():
    user_repo = _StubUserRepo()
    ps = _StubPasswordService()
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        password_hash=ps.hash("SamePass1"),
        status=UserStatus.ACTIVE,
    )
    user_repo.users[1] = user

    auth_service = AuthService(
        user_repo=user_repo,  # type: ignore[arg-type]
        rbac_repo=_StubRbacRepo(),  # type: ignore[arg-type]
        permission_cache=_StubPermissionCache(),  # type: ignore[arg-type]
        password_service=ps,  # type: ignore[arg-type]
        settings=_StubSettings(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValidationException, match="新密码不能与旧密码相同"):
        await auth_service.change_password(1, "SamePass1", "SamePass1")


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_old_password():
    user_repo = _StubUserRepo()
    ps = _StubPasswordService()
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        password_hash=ps.hash("RealPass1"),
        status=UserStatus.ACTIVE,
    )
    user_repo.users[1] = user

    auth_service = AuthService(
        user_repo=user_repo,  # type: ignore[arg-type]
        rbac_repo=_StubRbacRepo(),  # type: ignore[arg-type]
        permission_cache=_StubPermissionCache(),  # type: ignore[arg-type]
        password_service=ps,  # type: ignore[arg-type]
        settings=_StubSettings(),  # type: ignore[arg-type]
    )

    with pytest.raises(AuthenticationException, match="旧密码不正确"):
        await auth_service.change_password(1, "WrongPass1", "NewPass2")

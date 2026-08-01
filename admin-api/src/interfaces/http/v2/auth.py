"""认证相关路由：登录 / 刷新 / 当前用户 / 修改密码 / 登出。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.auth_service import AuthService
from src.interfaces.http.dependencies import (
    get_auth_service,
    get_current_permissions,
    get_current_user_id,
    get_user_service,
)
from src.application.services.user_service import UserService
from src.domain.rbac.policy import PermissionContext

from ._serializers import user_to_brief
from .schemas import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenPairSchema,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SuccessResponse[LoginResponse])
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[LoginResponse]:
    result = await auth_service.login(payload.username, payload.password)
    data = LoginResponse(
        user=user_to_brief(result.user),
        tokens=TokenPairSchema(
            access_token=result.tokens.access_token,
            refresh_token=result.tokens.refresh_token,
            expires_in=result.tokens.expires_in,
        ),
        role_names=sorted(result.permissions.role_names),
        permissions=sorted(result.permissions.role_permissions),
        password_change_required=result.password_change_required,
    )
    return SuccessResponse(data=data)


@router.post("/refresh", response_model=SuccessResponse[TokenPairSchema])
async def refresh_token(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[TokenPairSchema]:
    tokens = await auth_service.refresh(payload.refresh_token)
    return SuccessResponse(
        data=TokenPairSchema(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
        )
    )


@router.get("/me", response_model=SuccessResponse[CurrentUserResponse])
async def current_user(
    user_id: int = Depends(get_current_user_id),
    permissions: PermissionContext = Depends(get_current_permissions),
    user_service: UserService = Depends(get_user_service),
) -> SuccessResponse[CurrentUserResponse]:
    user = await user_service.get_user(user_id)
    return SuccessResponse(
        data=CurrentUserResponse(
            user=user_to_brief(user),
            role_names=sorted(permissions.role_names),
            permissions=sorted(permissions.role_permissions),
        )
    )


@router.post("/change-password", response_model=SuccessResponse[None])
async def change_password(
    payload: ChangePasswordRequest,
    user_id: int = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[None]:
    await auth_service.change_password(user_id, payload.old_password, payload.new_password)
    return SuccessResponse(message="密码修改成功")


@router.post("/logout", response_model=SuccessResponse[None])
async def logout(
    user_id: int = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[None]:
    await auth_service.invalidate_permission_cache(user_id)
    return SuccessResponse(message="已登出")

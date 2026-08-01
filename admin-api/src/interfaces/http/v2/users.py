"""用户管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.application.services.user_service import UserService
from src.domain.user.entities import UserStatus
from src.interfaces.http.dependencies import get_user_service, require_permission

from ._serializers import user_to_brief
from .schemas import (
    UserAssignRolesRequest,
    UserBriefSchema,
    UserCreateRequest,
    UserResetPasswordRequest,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[UserBriefSchema]],
    dependencies=[Depends(require_permission("user.read"))],
)
async def list_users(
    keyword: str | None = Query(default=None, max_length=64),
    status: UserStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[PageResponse[UserBriefSchema]]:
    items, total = await service.list_users(
        keyword=keyword, status=status, page=page, page_size=page_size
    )
    return SuccessResponse(
        data=PageResponse[UserBriefSchema](
            items=[user_to_brief(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "",
    response_model=SuccessResponse[UserBriefSchema],
    status_code=201,
    dependencies=[Depends(require_permission("user.write"))],
)
async def create_user(
    payload: UserCreateRequest,
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[UserBriefSchema]:
    user = await service.create_user(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role_ids=list(payload.role_ids),
    )
    return SuccessResponse(data=user_to_brief(user))


@router.get(
    "/{user_id}",
    response_model=SuccessResponse[UserBriefSchema],
    dependencies=[Depends(require_permission("user.read"))],
)
async def get_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[UserBriefSchema]:
    user = await service.get_user(user_id)
    return SuccessResponse(data=user_to_brief(user))


@router.patch(
    "/{user_id}",
    response_model=SuccessResponse[UserBriefSchema],
    dependencies=[Depends(require_permission("user.write"))],
)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[UserBriefSchema]:
    status = UserStatus(payload.status) if payload.status else None
    user = await service.update_profile(
        user_id,
        email=payload.email,
        display_name=payload.display_name,
        status=status,
    )
    return SuccessResponse(data=user_to_brief(user))


@router.post(
    "/{user_id}/reset-password",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("user.write"))],
)
async def reset_password(
    user_id: int,
    payload: UserResetPasswordRequest,
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[None]:
    await service.reset_password(user_id, payload.new_password)
    return SuccessResponse(message="密码重置成功")


@router.post(
    "/{user_id}/roles",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("user.write"))],
)
async def assign_roles(
    user_id: int,
    payload: UserAssignRolesRequest,
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[None]:
    await service.assign_roles(user_id, list(payload.role_ids))
    return SuccessResponse(message="角色分配成功")


@router.delete(
    "/{user_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("user.write"))],
)
async def delete_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
) -> SuccessResponse[None]:
    await service.delete_user(user_id)
    return SuccessResponse(message="用户删除成功")

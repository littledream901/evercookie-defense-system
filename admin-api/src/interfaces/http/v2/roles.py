"""角色管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.role_service import RoleService
from src.interfaces.http.dependencies import get_role_service, require_permission

from ._serializers import role_to_schema
from .schemas import RoleCreateRequest, RoleSchema, RoleUpdateRequest

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get(
    "",
    response_model=SuccessResponse[list[RoleSchema]],
    dependencies=[Depends(require_permission("role.read"))],
)
async def list_roles(
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[list[RoleSchema]]:
    roles = await service.list_roles()
    return SuccessResponse(data=[role_to_schema(r) for r in roles])


@router.post(
    "",
    response_model=SuccessResponse[RoleSchema],
    status_code=201,
    dependencies=[Depends(require_permission("role.write"))],
)
async def create_role(
    payload: RoleCreateRequest,
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[RoleSchema]:
    role = await service.create_role(
        name=payload.name,
        description=payload.description,
        permissions=list(payload.permissions),
    )
    return SuccessResponse(data=role_to_schema(role))


@router.get(
    "/{role_id}",
    response_model=SuccessResponse[RoleSchema],
    dependencies=[Depends(require_permission("role.read"))],
)
async def get_role(
    role_id: int,
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[RoleSchema]:
    role = await service.get_role(role_id)
    return SuccessResponse(data=role_to_schema(role))


@router.patch(
    "/{role_id}",
    response_model=SuccessResponse[RoleSchema],
    dependencies=[Depends(require_permission("role.write"))],
)
async def update_role(
    role_id: int,
    payload: RoleUpdateRequest,
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[RoleSchema]:
    role = await service.update_role(
        role_id,
        description=payload.description,
        permissions=list(payload.permissions) if payload.permissions is not None else None,
    )
    return SuccessResponse(data=role_to_schema(role))


@router.delete(
    "/{role_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("role.write"))],
)
async def delete_role(
    role_id: int,
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[None]:
    await service.delete_role(role_id)
    return SuccessResponse(message="角色删除成功")

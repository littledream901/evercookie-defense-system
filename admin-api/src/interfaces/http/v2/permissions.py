"""权限元数据路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.role_service import RoleService
from src.interfaces.http.dependencies import get_role_service, require_permission

from ._serializers import permission_to_schema
from .schemas import PermissionSchema, PermissionUpsertRequest

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get(
    "",
    response_model=SuccessResponse[list[PermissionSchema]],
    dependencies=[Depends(require_permission("permission.read"))],
)
async def list_permissions(
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[list[PermissionSchema]]:
    perms = await service.list_permissions()
    return SuccessResponse(data=[permission_to_schema(p) for p in perms])


@router.post(
    "",
    response_model=SuccessResponse[PermissionSchema],
    dependencies=[Depends(require_permission("permission.write"))],
)
async def upsert_permission(
    payload: PermissionUpsertRequest,
    service: RoleService = Depends(get_role_service),
) -> SuccessResponse[PermissionSchema]:
    perm = await service.upsert_permission(payload.code, payload.description)
    return SuccessResponse(data=permission_to_schema(perm))

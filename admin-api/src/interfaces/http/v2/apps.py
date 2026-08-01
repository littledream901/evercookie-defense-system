"""应用（App）管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.application.services.app_service import AppService
from src.domain.app.entities import ApplicationStatus
from src.interfaces.http.dependencies import (
    get_app_service,
    get_current_user_id,
    require_permission,
)

from ._serializers import app_to_schema
from .schemas import AppCreateRequest, AppSchema, AppUpdateRequest

router = APIRouter(prefix="/apps", tags=["apps"])


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[AppSchema]],
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_apps(
    keyword: str | None = Query(default=None, max_length=64),
    status: ApplicationStatus | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[PageResponse[AppSchema]]:
    items, total = await service.list_paged(
        keyword=keyword,
        status=status,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
    )
    return SuccessResponse(
        data=PageResponse[AppSchema](
            items=[app_to_schema(a) for a in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "",
    response_model=SuccessResponse[AppSchema],
    status_code=201,
    dependencies=[Depends(require_permission("app.write"))],
)
async def create_app(
    payload: AppCreateRequest,
    user_id: int = Depends(get_current_user_id),
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppSchema]:
    app = await service.create(
        name=payload.name,
        owner_user_id=user_id,
        description=payload.description,
        domains=list(payload.domains),
    )
    return SuccessResponse(data=app_to_schema(app))


@router.get(
    "/{app_id}",
    response_model=SuccessResponse[AppSchema],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_app(
    app_id: int,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppSchema]:
    app = await service.get(app_id)
    return SuccessResponse(data=app_to_schema(app))


@router.patch(
    "/{app_id}",
    response_model=SuccessResponse[AppSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def update_app(
    app_id: int,
    payload: AppUpdateRequest,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppSchema]:
    status = ApplicationStatus(payload.status) if payload.status else None
    app = await service.update(
        app_id,
        name=payload.name,
        description=payload.description,
        domains=list(payload.domains) if payload.domains is not None else None,
        status=status,
    )
    return SuccessResponse(data=app_to_schema(app))


@router.post(
    "/{app_id}/rotate-key",
    response_model=SuccessResponse[AppSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def rotate_key(
    app_id: int,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppSchema]:
    app = await service.rotate_api_key(app_id)
    return SuccessResponse(data=app_to_schema(app))


@router.delete(
    "/{app_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("app.write"))],
)
async def delete_app(
    app_id: int,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[None]:
    await service.delete(app_id)
    return SuccessResponse(message="应用删除成功")

"""页面资源 v2 HTTP 路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fangyu_shared.exceptions import PermissionDeniedException, ResourceNotFoundException
from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.application.services.page_resource_service import PageResourceService
from src.domain.page_resource.entities import PageResource, PageResourceKind
from src.interfaces.http.dependencies import (
    get_current_permissions,
    get_page_resource_service,
    require_permission,
)
from src.interfaces.http.v2.schemas import (
    PageResourceCreateRequest,
    PageResourceDetailResponse,
    PageResourceUpdateRequest,
)

router = APIRouter(
    prefix="/sites/{site_id}/page-resources",
    tags=["page-resources"],
)
global_router = APIRouter(prefix="/page-resources", tags=["page-resources"])


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[PageResourceDetailResponse]],
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_page_resources(
    site_id: Annotated[int, Path()],
    kind: Annotated[PageResourceKind | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    service: PageResourceService = Depends(get_page_resource_service),
):
    resources, total = await service.list_by_app(
        site_id, kind=kind, enabled=enabled, page=page, page_size=page_size
    )
    return SuccessResponse(
        data=PageResponse(
            items=[_to_detail_response(r) for r in resources],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "",
    response_model=SuccessResponse[PageResourceDetailResponse],
    status_code=201,
    dependencies=[Depends(require_permission("app.write"))],
)
async def create_page_resource(
    site_id: Annotated[int, Path()],
    req: PageResourceCreateRequest,
    service: PageResourceService = Depends(get_page_resource_service),
):
    resource = PageResource(
        id=None,
        app_id=site_id,
        name=req.name,
        kind=req.kind,
        content=req.content,
        content_type=req.content_type,
        enabled=req.enabled,
    )
    created = await service.create(resource)
    return SuccessResponse(data=_to_detail_response(created))


@router.get(
    "/{resource_id}",
    response_model=SuccessResponse[PageResourceDetailResponse],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_page_resource(
    site_id: Annotated[int, Path()],
    resource_id: Annotated[int, Path()],
    service: PageResourceService = Depends(get_page_resource_service),
):
    resource = await service.get(resource_id)
    if resource.app_id != site_id:
        raise ResourceNotFoundException(f"页面资源不存在: {resource_id}")
    return SuccessResponse(data=_to_detail_response(resource))


@router.put(
    "/{resource_id}",
    response_model=SuccessResponse[PageResourceDetailResponse],
    dependencies=[Depends(require_permission("app.write"))],
)
async def update_page_resource(
    site_id: Annotated[int, Path()],
    resource_id: Annotated[int, Path()],
    req: PageResourceUpdateRequest,
    service: PageResourceService = Depends(get_page_resource_service),
):
    current = await service.get(resource_id)
    if current.app_id != site_id:
        raise ResourceNotFoundException(f"页面资源不存在: {resource_id}")
    patch = PageResource(
        id=resource_id,
        app_id=site_id,
        name=req.name,
        kind=req.kind,
        content=req.content,
        content_type=req.content_type,
        enabled=req.enabled,
    )
    updated = await service.update(resource_id, patch)
    return SuccessResponse(data=_to_detail_response(updated))


@router.delete(
    "/{resource_id}",
    status_code=204,
    dependencies=[Depends(require_permission("app.write"))],
)
async def delete_page_resource(
    site_id: Annotated[int, Path()],
    resource_id: Annotated[int, Path()],
    service: PageResourceService = Depends(get_page_resource_service),
):
    current = await service.get(resource_id)
    if current.app_id != site_id:
        raise ResourceNotFoundException(f"页面资源不存在: {resource_id}")
    await service.delete(resource_id)


@router.post(
    "/sync",
    response_model=SuccessResponse[dict],
    dependencies=[Depends(require_permission("app.write"))],
)
async def sync_page_resources_cache(
    site_id: Annotated[int, Path()],
    service: PageResourceService = Depends(get_page_resource_service),
):
    """同步 app 的所有已启用资源到 Redis。"""
    count = await service.sync_enabled_to_cache(site_id)
    return SuccessResponse(data={"synced": count})


def _to_detail_response(r: PageResource) -> PageResourceDetailResponse:
    return PageResourceDetailResponse(
        id=r.id,
        app_id=r.app_id,
        name=r.name,
        kind=r.kind,
        content=r.content,
        content_type=r.content_type,
        enabled=r.enabled,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ── 全局页面资源（不限站点）─────────────────────────────────────────────

_GLOBAL_SITE = 0


@global_router.get(
    "",
    response_model=SuccessResponse[PageResponse[PageResourceDetailResponse]],
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_global_page_resources(
    kind: Annotated[PageResourceKind | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    service: PageResourceService = Depends(get_page_resource_service),
):
    resources, total = await service.list_by_app(
        _GLOBAL_SITE, kind=kind, enabled=enabled, page=page, page_size=page_size
    )
    return SuccessResponse(
        data=PageResponse(
            items=[_to_detail_response(r) for r in resources],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@global_router.post(
    "",
    response_model=SuccessResponse[PageResourceDetailResponse],
    status_code=201,
    dependencies=[Depends(require_permission("app.write"))],
)
async def create_global_page_resource(
    req: PageResourceCreateRequest,
    service: PageResourceService = Depends(get_page_resource_service),
):
    resource = PageResource(
        id=None,
        app_id=_GLOBAL_SITE,
        name=req.name,
        kind=req.kind,
        content=req.content,
        content_type=req.content_type,
        enabled=req.enabled,
    )
    created = await service.create(resource)
    return SuccessResponse(data=_to_detail_response(created))


@global_router.put(
    "/{resource_id}",
    response_model=SuccessResponse[PageResourceDetailResponse],
    dependencies=[Depends(require_permission("app.write"))],
)
async def update_global_page_resource(
    resource_id: Annotated[int, Path()],
    req: PageResourceUpdateRequest,
    service: PageResourceService = Depends(get_page_resource_service),
):
    patch = PageResource(
        id=resource_id,
        app_id=_GLOBAL_SITE,
        name=req.name,
        kind=req.kind,
        content=req.content,
        content_type=req.content_type,
        enabled=req.enabled,
    )
    updated = await service.update(resource_id, patch)
    return SuccessResponse(data=_to_detail_response(updated))


@global_router.delete(
    "/{resource_id}",
    status_code=204,
    dependencies=[Depends(require_permission("app.write"))],
)
async def delete_global_page_resource(
    resource_id: Annotated[int, Path()],
    service: PageResourceService = Depends(get_page_resource_service),
):
    await service.delete(resource_id)


@global_router.post(
    "/sync",
    response_model=SuccessResponse[dict],
    dependencies=[Depends(require_permission("app.write"))],
)
async def sync_global_page_resources_cache(
    service: PageResourceService = Depends(get_page_resource_service),
):
    count = await service.sync_enabled_to_cache(_GLOBAL_SITE)
    return SuccessResponse(data={"synced": count})

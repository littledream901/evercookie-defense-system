"""应用管理 API（V3 两层架构）。

应用是站点的业务分组容器，本身不参与 gateway 验签 ——
验签身份由其下的站点（``site_key``）承载。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.application.services.application_service import ApplicationService
from src.application.services.site_service import SiteService
from src.infrastructure.repositories.models import ApplicationModel
from src.interfaces.http.dependencies import (
    get_application_service,
    get_site_service,
    require_permission,
)
from src.interfaces.http.v2.sites import SiteResponse, _to_response as site_to_response

router = APIRouter(prefix="/applications", tags=["应用管理"])


class ApplicationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="应用名称")
    description: str = Field(default="", max_length=512, description="应用描述")
    owner_user_id: int | None = Field(default=None, description="所有者用户ID")


class ApplicationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128, description="应用名称")
    description: str | None = Field(default=None, max_length=512, description="应用描述")
    is_active: bool | None = Field(default=None, description="是否启用")


class ApplicationResponse(BaseModel):
    id: int
    app_key: str
    name: str
    description: str
    owner_user_id: int | None
    is_active: bool
    site_count: int = Field(default=0, description="站点数量")
    created_at: str
    updated_at: str


class ApplicationDetailResponse(ApplicationResponse):
    app_secret: str | None = Field(default=None, description="应用密钥（仅创建/轮换时返回）")


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int
    page_size: int


class SecretRotateResponse(BaseModel):
    app_id: int
    app_key: str
    app_secret: str
    message: str = "密钥已轮换，请妥善保存新密钥"


class SiteListOfAppResponse(BaseModel):
    items: list[SiteResponse]
    total: int


def _to_response(app: ApplicationModel, site_count: int = 0) -> ApplicationResponse:
    return ApplicationResponse(
        id=app.id,
        app_key=app.app_key,
        name=app.name,
        description=app.description,
        owner_user_id=app.owner_user_id,
        is_active=app.is_active,
        site_count=site_count,
        created_at=app.created_at.isoformat() if app.created_at else "",
        updated_at=app.updated_at.isoformat() if app.updated_at else "",
    )


@router.get("", response_model=ApplicationListResponse)
async def list_applications(
    keyword: str | None = Query(default=None, description="搜索关键词"),
    is_active: bool | None = Query(default=None, description="是否启用"),
    owner_id: int | None = Query(default=None, alias="ownerId", description="所有者ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize", description="每页大小"),
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.read")),
) -> ApplicationListResponse:
    """应用列表（分页）。"""
    apps, total = await app_service.list_paged(
        keyword=keyword,
        is_active=is_active,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
    )

    app_ids = [a.id for a in apps]
    site_counts = await app_service.count_sites_batch(app_ids)

    items = [_to_response(app, site_count=site_counts.get(app.id, 0)) for app in apps]

    return ApplicationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: int,
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.read")),
) -> ApplicationResponse:
    """获取应用详情。"""
    app = await app_service.get(app_id)
    site_count = await app_service.count_sites(app_id)
    return _to_response(app, site_count=site_count)


@router.post("", response_model=ApplicationDetailResponse, status_code=201)
async def create_application(
    req: ApplicationCreateRequest,
    app_service: ApplicationService = Depends(get_application_service),
    user: dict = Depends(require_permission("app.write")),
) -> ApplicationDetailResponse:
    """创建应用，返回 app_secret 明文。"""
    app, secret = await app_service.create(
        name=req.name,
        description=req.description,
        owner_user_id=req.owner_user_id or user.get("user_id"),
    )
    resp = _to_response(app, site_count=0)
    return ApplicationDetailResponse(**resp.model_dump(), app_secret=secret)


@router.put("/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: int,
    req: ApplicationUpdateRequest,
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.write")),
) -> ApplicationResponse:
    """更新应用。"""
    app = await app_service.update(
        app_id,
        name=req.name,
        description=req.description,
        is_active=req.is_active,
    )
    site_count = await app_service.count_sites(app_id)
    return _to_response(app, site_count=site_count)


@router.delete("/{app_id}", status_code=204)
async def delete_application(
    app_id: int,
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.write")),
) -> None:
    """删除应用。需先停用并清空所有站点。"""
    await app_service.delete(app_id)


@router.post("/{app_id}/rotate-secret", response_model=SecretRotateResponse)
async def rotate_application_secret(
    app_id: int,
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.write")),
) -> SecretRotateResponse:
    """轮换应用密钥。旧密钥立即失效。"""
    app, secret = await app_service.rotate_secret(app_id)
    return SecretRotateResponse(
        app_id=app.id,
        app_key=app.app_key,
        app_secret=secret,
    )


@router.get("/{app_id}/sites", response_model=SiteListOfAppResponse)
async def list_application_sites(
    app_id: int,
    app_service: ApplicationService = Depends(get_application_service),
    site_service: SiteService = Depends(get_site_service),
    _user: dict = Depends(require_permission("app.read")),
) -> SiteListOfAppResponse:
    """获取应用下的所有站点。"""
    app = await app_service.get(app_id)
    sites = await site_service.list_by_app(app_id)
    items = [site_to_response(s, app_name=app.name) for s in sites]
    return SiteListOfAppResponse(items=items, total=len(items))


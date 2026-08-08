"""应用管理 API（V3 两层架构）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.infrastructure.database import get_async_session
from src.infrastructure.repositories.application_repository import ApplicationRepository
from src.infrastructure.repositories.site_repository import SiteRepository
from src.interfaces.http.dependencies import require_permission
from sqlalchemy.ext.asyncio import AsyncSession
import secrets


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


@router.get("", response_model=ApplicationListResponse)
async def list_applications(
    keyword: str | None = Query(default=None, description="搜索关键词"),
    is_active: bool | None = Query(default=None, description="是否启用"),
    owner_id: int | None = Query(default=None, alias="ownerId", description="所有者ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize", description="每页大小"),
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("app:read")),
) -> ApplicationListResponse:
    """应用列表（分页）。"""
    repo = ApplicationRepository(session)
    site_repo = SiteRepository(session)
    
    offset = (page - 1) * page_size
    apps, total = await repo.list_paged(
        keyword=keyword,
        is_active=is_active,
        owner_id=owner_id,
        offset=offset,
        limit=page_size,
    )
    
    items = []
    for app in apps:
        site_count = await repo.count_sites(app.id)
        items.append(
            ApplicationResponse(
                id=app.id,
                app_key=app.app_key,
                name=app.name,
                description=app.description,
                owner_user_id=app.owner_user_id,
                is_active=app.is_active,
                site_count=site_count,
                created_at=app.created_at.isoformat(),
                updated_at=app.updated_at.isoformat(),
            )
        )
    
    return ApplicationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("app:read")),
) -> ApplicationResponse:
    """获取应用详情。"""
    repo = ApplicationRepository(session)
    app = await repo.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    site_count = await repo.count_sites(app.id)
    return ApplicationResponse(
        id=app.id,
        app_key=app.app_key,
        name=app.name,
        description=app.description,
        owner_user_id=app.owner_user_id,
        is_active=app.is_active,
        site_count=site_count,
        created_at=app.created_at.isoformat(),
        updated_at=app.updated_at.isoformat(),
    )


@router.post("", response_model=ApplicationDetailResponse, status_code=201)
async def create_application(
    req: ApplicationCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    user: dict = Depends(require_permission("app:write")),
) -> ApplicationDetailResponse:
    """创建应用。"""
    repo = ApplicationRepository(session)
    
    app_secret = secrets.token_urlsafe(32)
    app = await repo.create(
        name=req.name,
        description=req.description,
        owner_user_id=req.owner_user_id or user.get("user_id"),
        app_secret=app_secret,
    )
    await session.commit()
    
    return ApplicationDetailResponse(
        id=app.id,
        app_key=app.app_key,
        name=app.name,
        description=app.description,
        owner_user_id=app.owner_user_id,
        is_active=app.is_active,
        site_count=0,
        app_secret=app_secret,
        created_at=app.created_at.isoformat(),
        updated_at=app.updated_at.isoformat(),
    )


@router.put("/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: int,
    req: ApplicationUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("app:write")),
) -> ApplicationResponse:
    """更新应用。"""
    repo = ApplicationRepository(session)
    
    app = await repo.update(
        app_id,
        name=req.name,
        description=req.description,
        is_active=req.is_active,
    )
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    await session.commit()
    
    site_count = await repo.count_sites(app.id)
    return ApplicationResponse(
        id=app.id,
        app_key=app.app_key,
        name=app.name,
        description=app.description,
        owner_user_id=app.owner_user_id,
        is_active=app.is_active,
        site_count=site_count,
        created_at=app.created_at.isoformat(),
        updated_at=app.updated_at.isoformat(),
    )


@router.post("/{app_id}/rotate-secret", response_model=SecretRotateResponse)
async def rotate_application_secret(
    app_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("app:write")),
) -> SecretRotateResponse:
    """轮换应用密钥。"""
    repo = ApplicationRepository(session)
    
    app = await repo.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    new_secret = secrets.token_urlsafe(32)
    app = await repo.rotate_secret(app_id, new_secret)
    await session.commit()
    
    return SecretRotateResponse(
        app_id=app.id,
        app_key=app.app_key,
        app_secret=new_secret,
    )


@router.delete("/{app_id}", status_code=204)
async def delete_application(
    app_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("app:write")),
) -> None:
    """删除应用（级联删除所有站点）。"""
    repo = ApplicationRepository(session)
    site_repo = SiteRepository(session)
    
    app = await repo.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    site_count = await repo.count_sites(app_id)
    if site_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"应用下还有 {site_count} 个站点，请先删除所有站点后再删除应用"
        )
    
    await repo.delete(app_id)
    await session.commit()


@router.get("/{app_id}/sites")
async def list_application_sites(
    app_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("app:read")),
):
    """获取应用下的所有站点。"""
    from src.interfaces.http.v2.sites import SiteResponse
    
    app_repo = ApplicationRepository(session)
    app = await app_repo.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    site_repo = SiteRepository(session)
    sites = await site_repo.list_by_app(app_id)
    
    return {
        "items": [
            SiteResponse(
                id=site.id,
                site_key=site.site_key,
                app_id=site.app_id,
                app_name=app.name,
                name=site.name,
                domain=site.domain,
                alt_domains=site.alt_domains,
                access_mode=site.access_mode,
                sdk_version=site.sdk_version,
                gateway_url=site.gateway_url,
                is_active=site.is_active,
                created_at=site.created_at.isoformat(),
                updated_at=site.updated_at.isoformat(),
            )
            for site in sites
        ],
        "total": len(sites),
    }

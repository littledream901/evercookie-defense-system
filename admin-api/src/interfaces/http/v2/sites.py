"""站点管理 API（V3 两层架构）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.infrastructure.database import get_async_session
from src.infrastructure.repositories.application_repository import ApplicationRepository
from src.infrastructure.repositories.site_repository import SiteRepository
from src.interfaces.http.dependencies import require_permission
from sqlalchemy.ext.asyncio import AsyncSession
import secrets


router = APIRouter(prefix="/sites", tags=["站点管理"])


class SiteCreateRequest(BaseModel):
    app_id: int = Field(..., description="所属应用ID")
    name: str = Field(..., min_length=1, max_length=128, description="站点名称")
    domain: str = Field(..., min_length=1, max_length=512, description="主域名")
    alt_domains: list[str] = Field(default_factory=list, description="备用域名")
    access_mode: str = Field(default="adapter", description="接入模式：adapter/sdk")
    sdk_version: str | None = Field(default=None, description="SDK版本")
    gateway_url: str | None = Field(default=None, description="专属网关地址")
    clock_stats_enabled: bool = Field(default=True, description="是否启用频控统计")
    log_retention_days: int = Field(default=30, ge=1, le=365, description="日志保留天数")
    remark: str | None = Field(default=None, description="备注")


class SiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128, description="站点名称")
    alt_domains: list[str] | None = Field(default=None, description="备用域名")
    access_mode: str | None = Field(default=None, description="接入模式")
    sdk_version: str | None = Field(default=None, description="SDK版本")
    gateway_url: str | None = Field(default=None, description="专属网关地址")
    is_active: bool | None = Field(default=None, description="是否启用")
    clock_stats_enabled: bool | None = Field(default=None, description="是否启用频控统计")
    log_retention_days: int | None = Field(default=None, ge=1, le=365, description="日志保留天数")
    remark: str | None = Field(default=None, description="备注")


class SiteResponse(BaseModel):
    id: int
    site_key: str
    app_id: int
    app_name: str | None = Field(default=None, description="应用名称")
    name: str
    domain: str
    alt_domains: list[str]
    access_mode: str
    sdk_version: str | None
    gateway_url: str | None
    is_active: bool
    created_at: str
    updated_at: str


class SiteDetailResponse(SiteResponse):
    site_secret: str | None = Field(default=None, description="站点密钥（仅创建/轮换时返回）")
    clock_stats_enabled: bool
    log_retention_days: int
    remark: str | None


class SiteListResponse(BaseModel):
    items: list[SiteResponse]
    total: int
    page: int
    page_size: int


class SecretRotateResponse(BaseModel):
    site_id: int
    site_key: str
    site_secret: str
    message: str = "密钥已轮换，请妥善保存新密钥"


@router.get("", response_model=SiteListResponse)
async def list_sites(
    keyword: str | None = Query(default=None, description="搜索关键词"),
    app_id: int | None = Query(default=None, alias="appId", description="应用ID"),
    is_active: bool | None = Query(default=None, description="是否启用"),
    access_mode: str | None = Query(default=None, alias="accessMode", description="接入模式"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize", description="每页大小"),
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("site:read")),
) -> SiteListResponse:
    """站点列表（分页）。"""
    repo = SiteRepository(session)
    app_repo = ApplicationRepository(session)
    
    offset = (page - 1) * page_size
    sites, total = await repo.list_paged(
        keyword=keyword,
        app_id=app_id,
        is_active=is_active,
        access_mode=access_mode,
        offset=offset,
        limit=page_size,
    )
    
    app_ids = list({site.app_id for site in sites})
    app_map = {}
    for aid in app_ids:
        app = await app_repo.get(aid)
        if app:
            app_map[aid] = app.name
    
    items = [
        SiteResponse(
            id=site.id,
            site_key=site.site_key,
            app_id=site.app_id,
            app_name=app_map.get(site.app_id),
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
    ]
    
    return SiteListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{site_id}", response_model=SiteDetailResponse)
async def get_site(
    site_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("site:read")),
) -> SiteDetailResponse:
    """获取站点详情。"""
    repo = SiteRepository(session)
    app_repo = ApplicationRepository(session)
    
    site = await repo.get(site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="站点不存在")
    
    app = await app_repo.get(site.app_id)
    
    return SiteDetailResponse(
        id=site.id,
        site_key=site.site_key,
        app_id=site.app_id,
        app_name=app.name if app else None,
        name=site.name,
        domain=site.domain,
        alt_domains=site.alt_domains,
        access_mode=site.access_mode,
        sdk_version=site.sdk_version,
        gateway_url=site.gateway_url,
        is_active=site.is_active,
        clock_stats_enabled=site.clock_stats_enabled,
        log_retention_days=site.log_retention_days,
        remark=site.remark,
        created_at=site.created_at.isoformat(),
        updated_at=site.updated_at.isoformat(),
    )


@router.post("", response_model=SiteDetailResponse, status_code=201)
async def create_site(
    req: SiteCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("site:write")),
) -> SiteDetailResponse:
    """创建站点。"""
    app_repo = ApplicationRepository(session)
    site_repo = SiteRepository(session)
    
    app = await app_repo.get(req.app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    
    site_secret = secrets.token_urlsafe(32)
    site = await site_repo.create(
        app_id=req.app_id,
        name=req.name,
        domain=req.domain,
        alt_domains=req.alt_domains,
        access_mode=req.access_mode,
        site_secret=site_secret,
        sdk_version=req.sdk_version,
        gateway_url=req.gateway_url,
        clock_stats_enabled=req.clock_stats_enabled,
        log_retention_days=req.log_retention_days,
        remark=req.remark,
    )
    await session.commit()
    
    return SiteDetailResponse(
        id=site.id,
        site_key=site.site_key,
        app_id=site.app_id,
        app_name=app.name,
        name=site.name,
        domain=site.domain,
        alt_domains=site.alt_domains,
        access_mode=site.access_mode,
        site_secret=site_secret,
        sdk_version=site.sdk_version,
        gateway_url=site.gateway_url,
        is_active=site.is_active,
        clock_stats_enabled=site.clock_stats_enabled,
        log_retention_days=site.log_retention_days,
        remark=site.remark,
        created_at=site.created_at.isoformat(),
        updated_at=site.updated_at.isoformat(),
    )


@router.put("/{site_id}", response_model=SiteDetailResponse)
async def update_site(
    site_id: int,
    req: SiteUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("site:write")),
) -> SiteDetailResponse:
    """更新站点。"""
    repo = SiteRepository(session)
    app_repo = ApplicationRepository(session)
    
    site = await repo.update(
        site_id,
        name=req.name,
        alt_domains=req.alt_domains,
        access_mode=req.access_mode,
        sdk_version=req.sdk_version,
        gateway_url=req.gateway_url,
        is_active=req.is_active,
        clock_stats_enabled=req.clock_stats_enabled,
        log_retention_days=req.log_retention_days,
        remark=req.remark,
    )
    if site is None:
        raise HTTPException(status_code=404, detail="站点不存在")
    
    await session.commit()
    
    app = await app_repo.get(site.app_id)
    
    return SiteDetailResponse(
        id=site.id,
        site_key=site.site_key,
        app_id=site.app_id,
        app_name=app.name if app else None,
        name=site.name,
        domain=site.domain,
        alt_domains=site.alt_domains,
        access_mode=site.access_mode,
        sdk_version=site.sdk_version,
        gateway_url=site.gateway_url,
        is_active=site.is_active,
        clock_stats_enabled=site.clock_stats_enabled,
        log_retention_days=site.log_retention_days,
        remark=site.remark,
        created_at=site.created_at.isoformat(),
        updated_at=site.updated_at.isoformat(),
    )


@router.post("/{site_id}/rotate-secret", response_model=SecretRotateResponse)
async def rotate_site_secret(
    site_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("site:write")),
) -> SecretRotateResponse:
    """轮换站点密钥。"""
    repo = SiteRepository(session)
    
    site = await repo.get(site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="站点不存在")
    
    new_secret = secrets.token_urlsafe(32)
    site = await repo.rotate_secret(site_id, new_secret)
    await session.commit()
    
    return SecretRotateResponse(
        site_id=site.id,
        site_key=site.site_key,
        site_secret=new_secret,
    )


@router.delete("/{site_id}", status_code=204)
async def delete_site(
    site_id: int,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(require_permission("site:write")),
) -> None:
    """删除站点。"""
    repo = SiteRepository(session)
    
    site = await repo.get(site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="站点不存在")
    
    await repo.delete(site_id)
    await session.commit()

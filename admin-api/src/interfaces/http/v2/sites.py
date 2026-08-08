"""站点管理 API（V3 两层架构）。

站点是规则、页面资源、频控的挂载点，也是 gateway 验签的身份主体：
``site_key`` 用作 ``X-App-Key`` 请求头，``site.id`` 用作 SDK 的 ``appId``。
"""

from fangyu_shared.exceptions import BusinessRuleException, ResourceNotFoundException
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.application.services.application_service import ApplicationService
from src.application.services.rule_service import RuleService
from src.application.services.site_service import SiteService
from src.infrastructure.repositories.models import SiteModel
from src.interfaces.http.dependencies import (
    get_application_service,
    get_rule_service,
    get_site_service,
    require_permission,
)

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
    """站点更新请求。主域名创建后不可修改，故不含 domain。"""
    name: str | None = Field(default=None, min_length=1, max_length=128, description="站点名称")
    alt_domains: list[str] | None = Field(default=None, description="备用域名")
    access_mode: str | None = Field(default=None, description="接入模式")
    sdk_version: str | None = Field(default=None, description="SDK版本")
    gateway_url: str | None = Field(default=None, description="专属网关地址")
    is_active: bool | None = Field(default=None, description="是否启用")
    clock_stats_enabled: bool | None = Field(default=None, description="是否启用频控统计")
    log_retention_days: int | None = Field(default=None, ge=1, le=365, description="日志保留天数")
    remark: str | None = Field(default=None, description="备注")


class RuleBrief(BaseModel):
    """站点绑定的规则简要信息。"""
    name: str
    status: str


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
    clock_stats_enabled: bool
    log_retention_days: int
    remark: str | None
    created_at: str
    updated_at: str
    rule_count: int = Field(default=0, description="绑定的规则数量")
    rules: list[RuleBrief] = Field(default_factory=list, description="规则简要列表")


class SiteDetailResponse(SiteResponse):
    site_secret: str | None = Field(default=None, description="站点密钥（仅创建/轮换时返回）")


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


class BatchIdsRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, description="站点ID列表")


class BatchToggleRequest(BatchIdsRequest):
    is_active: bool = Field(..., description="目标启用状态")


class BatchUpdateRequest(BatchIdsRequest):
    access_mode: str | None = Field(default=None, description="接入模式")
    clock_stats_enabled: bool | None = Field(default=None, description="是否启用频控统计")
    log_retention_days: int | None = Field(default=None, ge=1, le=365, description="日志保留天数")


class BatchResultResponse(BaseModel):
    """批量操作结果。逐条容错，失败项附原因。"""
    succeeded: list[int] = Field(default_factory=list)
    failed: list[dict] = Field(default_factory=list)


class PublishResponse(BaseModel):
    site_id: int
    synced: int = Field(description="同步到 Redis 的规则数")


def _to_response(site: SiteModel, app_name: str | None = None, rule_count: int = 0, rules: list[RuleBrief] | None = None) -> SiteResponse:
    return SiteResponse(
        id=site.id,
        site_key=site.site_key,
        app_id=site.app_id,
        app_name=app_name,
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
        created_at=site.created_at.isoformat() if site.created_at else "",
        updated_at=site.updated_at.isoformat() if site.updated_at else "",
        rule_count=rule_count,
        rules=rules or [],
    )


@router.get("", response_model=SiteListResponse)
async def list_sites(
    keyword: str | None = Query(default=None, description="搜索关键词"),
    app_id: int | None = Query(default=None, alias="appId", description="应用ID"),
    is_active: bool | None = Query(default=None, description="是否启用"),
    access_mode: str | None = Query(default=None, alias="accessMode", description="接入模式"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize", description="每页大小"),
    site_service: SiteService = Depends(get_site_service),
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.read")),
) -> SiteListResponse:
    """站点列表（分页）。"""
    sites, total = await site_service.list_paged(
        keyword=keyword,
        app_id=app_id,
        is_active=is_active,
        access_mode=access_mode,
        page=page,
        page_size=page_size,
    )

    app_ids = list({s.app_id for s in sites})
    app_names = await app_service.get_names(app_ids)

    site_ids = [s.id for s in sites]
    rule_stats = await site_service.get_rule_stats(site_ids)

    items = []
    for site in sites:
        bound = rule_stats.get(site.id, [])
        items.append(
            _to_response(
                site,
                app_name=app_names.get(site.app_id),
                rule_count=len(bound),
                rules=[RuleBrief(name=name, status=status) for name, status in bound],
            )
        )

    return SiteListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{site_id}", response_model=SiteDetailResponse)
async def get_site(
    site_id: int,
    site_service: SiteService = Depends(get_site_service),
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.read")),
) -> SiteDetailResponse:
    """站点详情。"""
    site = await site_service.get(site_id)
    app = await app_service.get(site.app_id)
    bound = (await site_service.get_rule_stats([site_id])).get(site_id, [])
    rules = [RuleBrief(name=name, status=status) for name, status in bound]

    resp = _to_response(site, app_name=app.name, rule_count=len(rules), rules=rules)
    return SiteDetailResponse(**resp.model_dump())


@router.post("", response_model=SiteDetailResponse, status_code=201)
async def create_site(
    req: SiteCreateRequest,
    site_service: SiteService = Depends(get_site_service),
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.write")),
) -> SiteDetailResponse:
    """创建站点，返回 site_secret 明文。"""
    site, secret = await site_service.create(
        app_id=req.app_id,
        name=req.name,
        domain=req.domain,
        alt_domains=req.alt_domains,
        access_mode=req.access_mode,
        sdk_version=req.sdk_version,
        gateway_url=req.gateway_url,
        clock_stats_enabled=req.clock_stats_enabled,
        log_retention_days=req.log_retention_days,
        remark=req.remark,
    )
    app = await app_service.get(site.app_id)
    resp = _to_response(site, app_name=app.name)
    return SiteDetailResponse(**resp.model_dump(), site_secret=secret)


@router.post("/batch-delete", response_model=BatchResultResponse)
async def batch_delete_sites(
    req: BatchIdsRequest,
    site_service: SiteService = Depends(get_site_service),
    _user: dict = Depends(require_permission("app.write")),
) -> BatchResultResponse:
    """批量删除站点。逐条处理，单条失败不影响其余。"""
    succeeded, failed = await site_service.batch_delete(req.ids)
    return BatchResultResponse(succeeded=succeeded, failed=failed)


@router.post("/batch-toggle", response_model=BatchResultResponse)
async def batch_toggle_sites(
    req: BatchToggleRequest,
    site_service: SiteService = Depends(get_site_service),
    _user: dict = Depends(require_permission("app.write")),
) -> BatchResultResponse:
    """批量启停站点。停用会同步解绑 Redis 映射。"""
    succeeded, failed = await site_service.batch_set_active(req.ids, is_active=req.is_active)
    return BatchResultResponse(succeeded=succeeded, failed=failed)


@router.post("/batch-update", response_model=BatchResultResponse)
async def batch_update_sites(
    req: BatchUpdateRequest,
    site_service: SiteService = Depends(get_site_service),
    _user: dict = Depends(require_permission("app.write")),
) -> BatchResultResponse:
    """批量修改通用配置。"""
    succeeded, failed = await site_service.batch_update(
        req.ids,
        access_mode=req.access_mode,
        clock_stats_enabled=req.clock_stats_enabled,
        log_retention_days=req.log_retention_days,
    )
    return BatchResultResponse(succeeded=succeeded, failed=failed)


@router.post("/batch-publish", response_model=BatchResultResponse)
async def batch_publish_sites(
    req: BatchIdsRequest,
    site_service: SiteService = Depends(get_site_service),
    rule_service: RuleService = Depends(get_rule_service),
    _user: dict = Depends(require_permission("app.write")),
) -> BatchResultResponse:
    """批量把站点已发布规则重建到 Redis 分片。"""
    succeeded: list[int] = []
    failed: list[dict] = []
    for site_id in req.ids:
        try:
            await site_service.get(site_id)
            await rule_service.sync_published_to_cache(site_id)
            succeeded.append(site_id)
        except (ResourceNotFoundException, BusinessRuleException) as exc:
            failed.append({"id": str(site_id), "reason": str(exc)})
    return BatchResultResponse(succeeded=succeeded, failed=failed)


@router.post("/{site_id}/publish", response_model=PublishResponse)
async def publish_site_rules(
    site_id: int,
    site_service: SiteService = Depends(get_site_service),
    rule_service: RuleService = Depends(get_rule_service),
    _user: dict = Depends(require_permission("app.write")),
) -> PublishResponse:
    """把单个站点的已发布规则全量重建到 Redis 分片。"""
    await site_service.get(site_id)
    synced = await rule_service.sync_published_to_cache(site_id)
    return PublishResponse(site_id=site_id, synced=synced)


@router.put("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: int,
    req: SiteUpdateRequest,
    site_service: SiteService = Depends(get_site_service),
    app_service: ApplicationService = Depends(get_application_service),
    _user: dict = Depends(require_permission("app.write")),
) -> SiteResponse:
    """更新站点配置。主域名创建后不可修改。"""
    site = await site_service.update(
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
    app = await app_service.get(site.app_id)
    return _to_response(site, app_name=app.name)


@router.delete("/{site_id}", status_code=204)
async def delete_site(
    site_id: int,
    site_service: SiteService = Depends(get_site_service),
    _user: dict = Depends(require_permission("app.write")),
) -> None:
    """删除站点。需先停用。"""
    await site_service.delete(site_id)


@router.post("/{site_id}/rotate-secret", response_model=SecretRotateResponse)
async def rotate_site_secret(
    site_id: int,
    site_service: SiteService = Depends(get_site_service),
    _user: dict = Depends(require_permission("app.write")),
) -> SecretRotateResponse:
    """轮换站点密钥。旧密钥立即失效，需同步更新接入端配置。"""
    site, secret = await site_service.rotate_secret(site_id)
    return SecretRotateResponse(
        site_id=site.id,
        site_key=site.site_key,
        site_secret=secret,
    )

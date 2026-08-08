"""应用（App）管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.application.services.app_service import AppService
from src.application.services.rule_service import RuleService
from src.interfaces.http.dependencies import (
    get_app_repo,
    get_app_service,
    get_current_user_id,
    get_rule_service,
    require_permission,
)

from src.infrastructure.repositories.app_repository import AppRepository
from ._serializers import app_to_schema, app_to_schema_with_secret
from .schemas import (
    AppBatchDeleteRequest,
    AppBatchResult,
    AppBatchToggleRequest,
    AppBatchUpdateRequest,
    AppCreateRequest,
    AppCreateResponse,
    AppSchema,
    AppUpdateRequest,
    RuleBindResponse,
)

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[AppSchema]],
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_apps(
    keyword: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    service: AppService = Depends(get_app_service),
    app_repo: AppRepository = Depends(get_app_repo),
) -> SuccessResponse[PageResponse[AppSchema]]:
    items, total = await service.list_paged(
        keyword=keyword,
        status=status,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
    )
    # 批量查规则统计，不影响分页逻辑
    site_ids = [a.id for a in items if a.id is not None]
    rule_stats = await app_repo.get_rule_stats_for_sites(site_ids)
    return SuccessResponse(
        data=PageResponse[AppSchema](
            items=[
                app_to_schema(
                    a,
                    rules=rule_stats.get(a.id, []),
                )
                for a in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "",
    response_model=SuccessResponse[AppCreateResponse],
    status_code=201,
    dependencies=[Depends(require_permission("app.write"))],
)
async def create_app(
    payload: AppCreateRequest,
    user_id: int = Depends(get_current_user_id),
    service: AppService = Depends(get_app_service),
)-> SuccessResponse[AppCreateResponse]:
    app = await service.create(
        name=payload.name,
        owner_user_id=user_id,
        domain=payload.domain,
        alt_domains=list(payload.alt_domains),
        access_mode=payload.access_mode,
        sdk_version=payload.sdk_version,
        gateway_url=payload.gateway_url,
        clock_stats_enabled=payload.clock_stats_enabled,
        log_retention_days=payload.log_retention_days,
        remark=payload.remark,
    )
    return SuccessResponse(data=app_to_schema_with_secret(app))


# ── 批量操作 ───────────────────────────────────────────────────────────────
# 必须声明在 /{site_id} 之前，否则 "batch-delete" 会被当作 site_id 匹配。


@router.post(
    "/batch-delete",
    response_model=SuccessResponse[AppBatchResult],
    dependencies=[Depends(require_permission("app.write"))],
)
async def batch_delete_apps(
    payload: AppBatchDeleteRequest,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppBatchResult]:
    succeeded, failed = await service.batch_delete(payload.ids)
    return SuccessResponse(
        data=AppBatchResult(succeeded=succeeded, failed=failed),
        message=f"已删除 {len(succeeded)} 个站点" + (f"，{len(failed)} 个失败" if failed else ""),
    )


@router.post(
    "/batch-toggle",
    response_model=SuccessResponse[AppBatchResult],
    dependencies=[Depends(require_permission("app.write"))],
)
async def batch_toggle_apps(
    payload: AppBatchToggleRequest,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppBatchResult]:
    succeeded, failed = await service.batch_set_active(payload.ids, is_active=payload.is_active)
    action = "启用" if payload.is_active else "停用"
    return SuccessResponse(
        data=AppBatchResult(succeeded=succeeded, failed=failed),
        message=f"已{action} {len(succeeded)} 个站点" + (f"，{len(failed)} 个失败" if failed else ""),
    )


@router.post(
    "/batch-update",
    response_model=SuccessResponse[AppBatchResult],
    dependencies=[Depends(require_permission("app.write"))],
)
async def batch_update_apps(
    payload: AppBatchUpdateRequest,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppBatchResult]:
    succeeded, failed = await service.batch_update(
        payload.ids,
        access_mode=payload.access_mode,
        clock_stats_enabled=payload.clock_stats_enabled,
        log_retention_days=payload.log_retention_days,
    )
    return SuccessResponse(
        data=AppBatchResult(succeeded=succeeded, failed=failed),
        message=f"已更新 {len(succeeded)} 个站点" + (f"，{len(failed)} 个失败" if failed else ""),
    )


class BatchPublishRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


@router.post(
    "/batch-publish",
    response_model=SuccessResponse[AppBatchResult],
    dependencies=[Depends(require_permission("app.write"))],
)
async def batch_publish_apps(
    payload: BatchPublishRequest,
    app_service: AppService = Depends(get_app_service),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AppBatchResult]:
    """批量发布：逐站点同步已发布规则到 Redis，失败项不影响其他项。"""
    succeeded: list[int] = []
    failed: list[dict[str, str]] = []
    for site_id in payload.ids:
        try:
            await app_service.get(site_id)
            await rule_service.sync_published_to_cache(site_id)
            succeeded.append(site_id)
        except Exception as exc:
            failed.append({"id": str(site_id), "reason": str(exc)})
    return SuccessResponse(
        data=AppBatchResult(succeeded=succeeded, failed=failed),
        message=f"已发布 {len(succeeded)} 个站点" + (f"，{len(failed)} 个失败" if failed else ""),
    )


@router.get(
    "/{site_id}",
    response_model=SuccessResponse[AppSchema],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_app(
    site_id: int,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppSchema]:
    app = await service.get(site_id)
    return SuccessResponse(data=app_to_schema(app))


@router.patch(
    "/{site_id}",
    response_model=SuccessResponse[AppSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def update_app(
    site_id: int,
    payload: AppUpdateRequest,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppSchema]:
    app = await service.update(
        site_id,
        name=payload.name,
        alt_domains=list(payload.alt_domains) if payload.alt_domains is not None else None,
        access_mode=payload.access_mode,
        sdk_version=payload.sdk_version,
        gateway_url=payload.gateway_url,
        is_active=payload.is_active,
        clock_stats_enabled=payload.clock_stats_enabled,
        log_retention_days=payload.log_retention_days,
        remark=payload.remark,
    )
    return SuccessResponse(data=app_to_schema(app))


@router.post(
    "/{site_id}/rotate-key",
    response_model=SuccessResponse[AppCreateResponse],
    dependencies=[Depends(require_permission("app.write"))],
)
async def rotate_key(
    site_id: int,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[AppCreateResponse]:
    app = await service.rotate_api_key(site_id)
    return SuccessResponse(data=app_to_schema_with_secret(app))


@router.delete(
    "/{site_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("app.write"))],
)
async def delete_app(
    site_id: int,
    service: AppService = Depends(get_app_service),
) -> SuccessResponse[None]:
    await service.delete(site_id)
    return SuccessResponse(message="应用删除成功")


@router.post(
    "/{site_id}/publish",
    response_model=SuccessResponse[dict],
    dependencies=[Depends(require_permission("app.write"))],
)
async def publish_snapshot(
    site_id: int,
    app_service: AppService = Depends(get_app_service),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[dict]:
    """发布站点：将该站点已发布的规则全量同步到 Redis 分片。"""
    from datetime import datetime, timezone
    await app_service.get(site_id)  # 不存在时抛 404
    synced = await rule_service.sync_published_to_cache(site_id)
    published_at = datetime.now(timezone.utc).isoformat()
    return SuccessResponse(data={"ok": True, "published_at": published_at, "synced": synced})

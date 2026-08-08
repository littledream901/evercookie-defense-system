"""规则管理路由（含版本、发布、回滚、缓存同步）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fangyu_shared.schemas.common import PageResponse, SuccessResponse
from fangyu_shared.schemas.rule import (
    DecisionRule,
    RuleKind,
    RuleStatus,
    ScoringRule,
)

from src.application.services.rule_service import RuleService
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_rule_service,
    require_permission,
)

from .schemas import RuleRollbackRequest, RuleUpsertRequest

router = APIRouter(prefix="/sites/{site_id}/rules", tags=["rules"])


AnyRule = DecisionRule | ScoringRule


def _to_domain(site_id: int | None, payload: RuleUpsertRequest) -> AnyRule:
    """DTO → 领域对象。字段互斥性已由 RuleUpsertRequest 校验器保证。"""
    common = {
        "id": None,
        "appId": site_id if site_id is not None else 0,
        "name": payload.name,
        "description": payload.description,
        "status": RuleStatus.DRAFT,
        "priority": payload.priority,
        "conditions": list(payload.conditions),
        "matchAll": payload.match_all,
        "group": payload.group,
        "tags": list(payload.tags),
        "version": 1,
    }
    if payload.kind == RuleKind.SCORING:
        return ScoringRule(kind=RuleKind.SCORING, weight=payload.weight or 0, **common)
    assert payload.disposition_match is not None
    assert payload.disposition_miss is not None
    return DecisionRule(
        kind=RuleKind.DECISION,
        disposition_match=payload.disposition_match,
        disposition_miss=payload.disposition_miss,
        **common,
    )


def _check_rule_access(rule: AnyRule, site_id: int) -> None:
    """校验规则是否对当前站点可见。全局规则（app_id=0）对所有站点可见。"""
    if rule.app_id == 0:
        return
    if site_id not in rule.site_ids:
        raise HTTPException(status_code=404, detail="规则不存在")


# ── 站点级路由 ────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SuccessResponse[PageResponse[AnyRule]],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def list_rules(
    site_id: int,
    keyword: str | None = Query(default=None, max_length=64),
    status: RuleStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[PageResponse[AnyRule]]:
    items, total = await service.list_all(
        site_id=site_id,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return SuccessResponse(
        data=PageResponse[AnyRule](
            items=items, total=total, page=page, page_size=page_size
        )
    )


@router.post(
    "",
    response_model=SuccessResponse[AnyRule],
    status_code=201,
    dependencies=[Depends(require_permission("rule.write"))],
)
async def create_rule(
    site_id: int,
    payload: RuleUpsertRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.create(_to_domain(site_id, payload), author_id=user_id, site_ids=[site_id])
    return SuccessResponse(data=rule)


@router.get(
    "/{rule_id}",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def get_rule(
    site_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    return SuccessResponse(data=rule)


@router.put(
    "/{rule_id}",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def update_rule(
    site_id: int,
    rule_id: int,
    payload: RuleUpsertRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.update(rule_id, _to_domain(site_id, payload), author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/publish",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def publish_rule(
    site_id: int,
    rule_id: int,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.publish(rule_id, author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/shadow",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def shadow_rule(
    site_id: int,
    rule_id: int,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    """把规则置为灰度影子：下发到 gateway 求值但不影响真实处置。

    权限沿用 rule.publish 而非 rule.write：这是一次下发到数据面的操作，
    风险等级与发布同级（会改变 gateway 读到的规则集），不该让只有编辑权
    的人触发。
    """
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.to_shadow(rule_id, author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/disable",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def disable_rule(
    site_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.disable(rule_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/archive",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def archive_rule(
    site_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.archive(rule_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/unarchive",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def unarchive_rule(
    site_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    """规则恢复为草稿：归档规则恢复编辑，或影子规则退回修改。"""
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.unarchive(rule_id)
    return SuccessResponse(data=rule)


@router.delete(
    "/{rule_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def delete_rule(
    site_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[None]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    await service.delete(rule_id)
    return SuccessResponse(message="规则删除成功")


@router.get(
    "/{rule_id}/versions",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def list_versions(
    site_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    versions = await service.list_versions(rule_id)
    return SuccessResponse(
        data=[
            {
                "id": v.id,
                "rule_id": v.rule_id,
                "version": v.version,
                "author_id": v.author_id,
                "change_summary": v.change_summary,
                "created_at": v.created_at,
                "published_at": v.published_at,
                "snapshot": v.snapshot,
            }
            for v in versions
        ]
    )


@router.post(
    "/{rule_id}/rollback",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def rollback_rule(
    site_id: int,
    rule_id: int,
    payload: RuleRollbackRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.get(rule_id)
    _check_rule_access(rule, site_id)
    rule = await service.rollback(rule_id, payload.target_version, author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/sync-cache",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def sync_cache(
    site_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[dict[str, int]]:
    count = await service.sync_published_to_cache(site_id)
    return SuccessResponse(data={"synced": count})


# ── 全局规则路由（不依赖 site_id）──────────────────────────────────────────
global_router = APIRouter(prefix="/rules", tags=["rules"])


class SetSitesRequest(BaseModel):
    site_ids: list[int]


class BindRulesRequest(BaseModel):
    rule_ids: list[int]


@global_router.get(
    "",
    response_model=SuccessResponse[PageResponse[AnyRule]],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def list_all_rules(
    keyword: str | None = Query(default=None, max_length=64),
    status: RuleStatus | None = Query(default=None),
    site_id: int | None = Query(default=None, alias="siteId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[PageResponse[AnyRule]]:
    items, total = await service.list_all(
        status=status, keyword=keyword, site_id=site_id, page=page, page_size=page_size
    )
    return SuccessResponse(
        data=PageResponse[AnyRule](items=items, total=total, page=page, page_size=page_size)
    )


@global_router.post(
    "",
    response_model=SuccessResponse[AnyRule],
    status_code=201,
    dependencies=[Depends(require_permission("rule.write"))],
)
async def create_global_rule(
    payload: RuleUpsertRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = _to_domain(None, payload)
    created = await service.create(rule, author_id=user_id)
    return SuccessResponse(data=created)


@global_router.post(
    "/{rule_id}/set-sites",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def set_rule_sites(
    rule_id: int,
    payload: SetSitesRequest,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    """全量覆盖一条规则绑定的站点列表。"""
    updated = await service.set_sites(rule_id, payload.site_ids)
    return SuccessResponse(data=updated)


@global_router.post(
    "/bind-to-site/{site_id}",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def bind_rules_to_site(
    site_id: int,
    payload: BindRulesRequest,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[dict[str, Any]]:
    """全量覆盖某站点绑定的规则列表，并重建该站点缓存分片。
    
    返回绑定数量和冲突检测结果。
    """
    count, conflict_info = await service.bind_rules_to_site(site_id, payload.rule_ids)
    return SuccessResponse(
        data={
            "bound": count,
            "conflicts": conflict_info,
        }
    )

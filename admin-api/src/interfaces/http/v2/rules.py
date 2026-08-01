"""规则管理路由（含版本、发布、回滚、缓存同步）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

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

router = APIRouter(prefix="/apps/{app_id}/rules", tags=["rules"])


AnyRule = DecisionRule | ScoringRule


def _to_domain(app_id: int, payload: RuleUpsertRequest) -> AnyRule:
    """DTO → 领域对象。字段互斥性已由 RuleUpsertRequest 校验器保证。"""
    common = {
        "id": None,
        "appId": app_id,
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
    assert payload.disposition is not None
    return DecisionRule(kind=RuleKind.DECISION, disposition=payload.disposition, **common)


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[AnyRule]],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def list_rules(
    app_id: int,
    keyword: str | None = Query(default=None, max_length=64),
    status: RuleStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[PageResponse[AnyRule]]:
    items, total = await service.list_by_app(
        app_id,
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
    app_id: int,
    payload: RuleUpsertRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.create(_to_domain(app_id, payload), author_id=user_id)
    return SuccessResponse(data=rule)


@router.get(
    "/{rule_id}",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def get_rule(
    app_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    _ = app_id  # 路径校验将来可加：确保规则属于该 app
    rule = await service.get(rule_id)
    return SuccessResponse(data=rule)


@router.put(
    "/{rule_id}",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def update_rule(
    app_id: int,
    rule_id: int,
    payload: RuleUpsertRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    rule = await service.update(rule_id, _to_domain(app_id, payload), author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/publish",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def publish_rule(
    app_id: int,
    rule_id: int,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    _ = app_id
    rule = await service.publish(rule_id, author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/disable",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def disable_rule(
    app_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    _ = app_id
    rule = await service.disable(rule_id)
    return SuccessResponse(data=rule)


@router.post(
    "/{rule_id}/archive",
    response_model=SuccessResponse[AnyRule],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def archive_rule(
    app_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    _ = app_id
    rule = await service.archive(rule_id)
    return SuccessResponse(data=rule)


@router.delete(
    "/{rule_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_permission("rule.write"))],
)
async def delete_rule(
    app_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[None]:
    _ = app_id
    await service.delete(rule_id)
    return SuccessResponse(message="规则删除成功")


@router.get(
    "/{rule_id}/versions",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def list_versions(
    app_id: int,
    rule_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    _ = app_id
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
    app_id: int,
    rule_id: int,
    payload: RuleRollbackRequest,
    user_id: int = Depends(get_current_user_id),
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[AnyRule]:
    _ = app_id
    rule = await service.rollback(rule_id, payload.target_version, author_id=user_id)
    return SuccessResponse(data=rule)


@router.post(
    "/sync-cache",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("rule.publish"))],
)
async def sync_cache(
    app_id: int,
    service: RuleService = Depends(get_rule_service),
) -> SuccessResponse[dict[str, int]]:
    count = await service.sync_published_to_cache(app_id)
    return SuccessResponse(data={"synced": count})

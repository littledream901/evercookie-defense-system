"""规则组管理接口。"""

from __future__ import annotations

from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.rule import RuleGroup
from fastapi import APIRouter, Depends

from src.application.services.rule_group_service import RuleGroupService
from src.interfaces.http.dependencies import get_rule_group_service, require_permission
from src.interfaces.http.v2.schemas import RuleGroupUpsertRequest

router = APIRouter(tags=["rule_groups"])


@router.get(
    "/api/v2/sites/{site_id}/rule-groups",
    summary="查询站点的规则组列表",
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_rule_groups(
    site_id: int,
    service: RuleGroupService = Depends(get_rule_group_service),
) -> SuccessResponse[list[RuleGroup]]:
    groups = await service.list_by_site(site_id)
    return SuccessResponse(data=groups)


@router.get(
    "/api/v2/rule-groups/{group_id}",
    summary="获取规则组详情",
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_rule_group(
    group_id: int,
    service: RuleGroupService = Depends(get_rule_group_service),
) -> SuccessResponse[RuleGroup]:
    group = await service.get(group_id)
    return SuccessResponse(data=group)


@router.post(
    "/api/v2/sites/{site_id}/rule-groups",
    summary="创建规则组",
    dependencies=[Depends(require_permission("app.write"))],
)
async def create_rule_group(
    site_id: int,
    req: RuleGroupUpsertRequest,
    service: RuleGroupService = Depends(get_rule_group_service),
) -> SuccessResponse[RuleGroup]:
    group = await service.create(
        site_id=site_id,
        name=req.name,
        mode=req.mode,
        priority=req.priority,
        enabled=req.enabled,
        on_no_match=req.on_no_match,
    )
    return SuccessResponse(data=group)


@router.put(
    "/api/v2/rule-groups/{group_id}",
    summary="更新规则组",
    dependencies=[Depends(require_permission("app.write"))],
)
async def update_rule_group(
    group_id: int,
    req: RuleGroupUpsertRequest,
    service: RuleGroupService = Depends(get_rule_group_service),
) -> SuccessResponse[RuleGroup]:
    group = await service.update(
        group_id=group_id,
        name=req.name,
        mode=req.mode,
        priority=req.priority,
        enabled=req.enabled,
        on_no_match=req.on_no_match,
    )
    return SuccessResponse(data=group)


@router.delete(
    "/api/v2/rule-groups/{group_id}",
    summary="删除规则组",
    dependencies=[Depends(require_permission("app.write"))],
)
async def delete_rule_group(
    group_id: int,
    service: RuleGroupService = Depends(get_rule_group_service),
) -> SuccessResponse[None]:
    await service.delete(group_id)
    return SuccessResponse(data=None)


@router.post(
    "/api/v2/sites/{site_id}/rule-groups/sync",
    summary="全量同步规则组到 Redis",
    dependencies=[Depends(require_permission("app.write"))],
)
async def sync_rule_groups(
    site_id: int,
    service: RuleGroupService = Depends(get_rule_group_service),
) -> SuccessResponse[dict[str, int]]:
    count = await service.sync_site_to_cache(site_id)
    return SuccessResponse(data={"synced": count})

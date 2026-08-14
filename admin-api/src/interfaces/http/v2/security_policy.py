"""安全策略 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.security import SecurityPolicy

from src.application.services.security_policy_service import SecurityPolicyService
from src.interfaces.http.dependencies import (
    get_security_policy_service,
    require_permission,
)

router = APIRouter(prefix="/sites", tags=["security-policy"])


@router.get(
    "/{site_id}/security-policy",
    response_model=SuccessResponse[SecurityPolicy],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_security_policy(
    site_id: int,
    service: SecurityPolicyService = Depends(get_security_policy_service),
) -> SuccessResponse[SecurityPolicy]:
    """获取站点安全策略配置（未配置时返回默认值）。"""
    policy = await service.get_policy(site_id)
    return SuccessResponse(data=policy)


@router.put(
    "/{site_id}/security-policy",
    response_model=SuccessResponse[SecurityPolicy],
    dependencies=[Depends(require_permission("app.write"))],
)
async def update_security_policy(
    site_id: int,
    policy: SecurityPolicy,
    service: SecurityPolicyService = Depends(get_security_policy_service),
) -> SuccessResponse[SecurityPolicy]:
    """更新站点安全策略配置。"""
    # 确保 site_id 匹配
    policy.site_id = site_id
    updated = await service.update_policy(policy)
    return SuccessResponse(data=updated)


@router.delete(
    "/{site_id}/security-policy",
    status_code=204,
    response_model=None,
    dependencies=[Depends(require_permission("app.write"))],
)
async def reset_security_policy(
    site_id: int,
    service: SecurityPolicyService = Depends(get_security_policy_service),
) -> None:
    """重置站点安全策略为默认值（删除自定义配置）。"""
    await service.reset_policy(site_id)

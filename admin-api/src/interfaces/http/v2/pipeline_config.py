"""流水线配置路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.pipeline import PipelineConfig

from src.application.services.pipeline_config_service import PipelineConfigService
from src.interfaces.http.dependencies import get_pipeline_config_service, require_permission

router = APIRouter(prefix="/sites", tags=["pipeline-config"])


@router.get(
    "/{site_id}/pipeline-config",
    response_model=SuccessResponse[PipelineConfig],
    dependencies=[Depends(require_permission("site.read"))],
)
async def get_pipeline_config(
    site_id: int,
    service: PipelineConfigService = Depends(get_pipeline_config_service),
) -> SuccessResponse[PipelineConfig]:
    """获取站点的流水线配置。"""
    config = await service.get_config(site_id)
    return SuccessResponse(data=config)


@router.put(
    "/{site_id}/pipeline-config",
    response_model=SuccessResponse[PipelineConfig],
    dependencies=[Depends(require_permission("site.write"))],
)
async def update_pipeline_config(
    site_id: int,
    payload: PipelineConfig,
    service: PipelineConfigService = Depends(get_pipeline_config_service),
) -> SuccessResponse[PipelineConfig]:
    """更新站点的流水线配置。"""
    config = await service.update_config(site_id, payload)
    return SuccessResponse(data=config)

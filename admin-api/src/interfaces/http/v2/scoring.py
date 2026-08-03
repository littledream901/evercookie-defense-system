"""评分配置路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.scoring_service import ScoringService
from src.infrastructure.repositories.models import ScoringConfigModel
from src.interfaces.http.dependencies import get_scoring_service, require_permission
from src.interfaces.http.v2.schemas import ScoringConfigSchema, ScoringConfigUpsertRequest

router = APIRouter(tags=["scoring"])


def _to_schema(row: ScoringConfigModel) -> ScoringConfigSchema:
    return ScoringConfigSchema(
        id=row.id,
        app_id=row.app_id,
        name=row.name,
        enabled=row.enabled,
        threshold_suspect=row.threshold_suspect,
        threshold_hostile=row.threshold_hostile,
        weights=dict(row.weights or {}),
        disposition_suspect=row.disposition_suspect,
        disposition_hostile=row.disposition_hostile,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/scoring/global",
    response_model=SuccessResponse[ScoringConfigSchema | None],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_global_scoring_config(
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[ScoringConfigSchema | None]:
    """全局评分配置（不绑定特定站点）。"""
    row = await service.get(0)
    return SuccessResponse(data=_to_schema(row) if row else None)


@router.put(
    "/scoring/global",
    response_model=SuccessResponse[ScoringConfigSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def put_global_scoring_config(
    payload: ScoringConfigUpsertRequest,
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[ScoringConfigSchema]:
    row = await service.upsert(
        0,
        name=payload.name,
        enabled=payload.enabled,
        threshold_suspect=payload.threshold_suspect,
        threshold_hostile=payload.threshold_hostile,
        weights=dict(payload.weights),
        disposition_suspect=payload.disposition_suspect.model_dump(mode="json") if payload.disposition_suspect else None,
        disposition_hostile=payload.disposition_hostile.model_dump(mode="json") if payload.disposition_hostile else None,
    )
    return SuccessResponse(data=_to_schema(row))


@router.delete(
    "/scoring/global",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("app.write"))],
)
async def reset_global_scoring_config(
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[dict[str, bool]]:
    deleted = await service.reset(0)
    return SuccessResponse(data={"deleted": deleted})


@router.get(
    "/sites/{site_id}/scoring",
    response_model=SuccessResponse[ScoringConfigSchema | None],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_scoring_config(
    site_id: int,
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[ScoringConfigSchema | None]:
    row = await service.get(site_id)
    return SuccessResponse(data=_to_schema(row) if row else None)


@router.put(
    "/sites/{site_id}/scoring",
    response_model=SuccessResponse[ScoringConfigSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def put_scoring_config(
    site_id: int,
    payload: ScoringConfigUpsertRequest,
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[ScoringConfigSchema]:
    row = await service.upsert(
        site_id,
        name=payload.name,
        enabled=payload.enabled,
        threshold_suspect=payload.threshold_suspect,
        threshold_hostile=payload.threshold_hostile,
        weights=dict(payload.weights),
        disposition_suspect=payload.disposition_suspect.model_dump(mode="json") if payload.disposition_suspect else None,
        disposition_hostile=payload.disposition_hostile.model_dump(mode="json") if payload.disposition_hostile else None,
    )
    return SuccessResponse(data=_to_schema(row))


@router.delete(
    "/sites/{site_id}/scoring",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("app.write"))],
)
async def reset_scoring_config(
    site_id: int,
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[dict[str, bool]]:
    deleted = await service.reset(site_id)
    return SuccessResponse(data={"deleted": deleted})


@router.get(
    "/scoring/dimensions",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("app.read"))],
)
async def list_scoring_dimensions(
    service: ScoringService = Depends(get_scoring_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    return SuccessResponse(data=service.list_dimensions())

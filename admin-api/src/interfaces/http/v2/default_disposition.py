"""默认处置路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.disposition import Disposition

from src.application.services.default_disposition_service import DefaultDispositionService
from src.infrastructure.repositories.models import DefaultDispositionModel
from src.interfaces.http.dependencies import (
    get_default_disposition_service,
    require_permission,
)
from src.interfaces.http.v2.schemas import (
    DefaultDispositionSchema,
    DefaultDispositionUpsertRequest,
)

router = APIRouter(tags=["default-disposition"])


def _to_schema(row: DefaultDispositionModel) -> DefaultDispositionSchema:
    return DefaultDispositionSchema(
        id=row.id,
        site_id=row.site_id,
        disposition=Disposition.model_validate(row.disposition),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _full_disposition(payload: DefaultDispositionUpsertRequest) -> dict:
    """把入参 DecisionDisposition 推导为完整 Disposition 后序列化为 camelCase dict。"""
    return payload.disposition.to_disposition().model_dump(mode="json", by_alias=True)


@router.get(
    "/default-disposition/global",
    response_model=SuccessResponse[DefaultDispositionSchema | None],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_global_default_disposition(
    service: DefaultDispositionService = Depends(get_default_disposition_service),
) -> SuccessResponse[DefaultDispositionSchema | None]:
    """全局默认处置（不绑定特定站点，site_id=0）。"""
    row = await service.get(0)
    return SuccessResponse(data=_to_schema(row) if row else None)


@router.put(
    "/default-disposition/global",
    response_model=SuccessResponse[DefaultDispositionSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def put_global_default_disposition(
    payload: DefaultDispositionUpsertRequest,
    service: DefaultDispositionService = Depends(get_default_disposition_service),
) -> SuccessResponse[DefaultDispositionSchema]:
    row = await service.upsert(0, disposition=_full_disposition(payload))
    return SuccessResponse(data=_to_schema(row))


@router.delete(
    "/default-disposition/global",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("app.write"))],
)
async def reset_global_default_disposition(
    service: DefaultDispositionService = Depends(get_default_disposition_service),
) -> SuccessResponse[dict[str, bool]]:
    deleted = await service.reset(0)
    return SuccessResponse(data={"deleted": deleted})


@router.get(
    "/sites/{site_id}/default-disposition",
    response_model=SuccessResponse[DefaultDispositionSchema | None],
    dependencies=[Depends(require_permission("app.read"))],
)
async def get_default_disposition(
    site_id: int,
    service: DefaultDispositionService = Depends(get_default_disposition_service),
) -> SuccessResponse[DefaultDispositionSchema | None]:
    row = await service.get(site_id)
    return SuccessResponse(data=_to_schema(row) if row else None)


@router.put(
    "/sites/{site_id}/default-disposition",
    response_model=SuccessResponse[DefaultDispositionSchema],
    dependencies=[Depends(require_permission("app.write"))],
)
async def put_default_disposition(
    site_id: int,
    payload: DefaultDispositionUpsertRequest,
    service: DefaultDispositionService = Depends(get_default_disposition_service),
) -> SuccessResponse[DefaultDispositionSchema]:
    row = await service.upsert(site_id, disposition=_full_disposition(payload))
    return SuccessResponse(data=_to_schema(row))


@router.delete(
    "/sites/{site_id}/default-disposition",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("app.write"))],
)
async def reset_default_disposition(
    site_id: int,
    service: DefaultDispositionService = Depends(get_default_disposition_service),
) -> SuccessResponse[dict[str, bool]]:
    deleted = await service.reset(site_id)
    return SuccessResponse(data={"deleted": deleted})

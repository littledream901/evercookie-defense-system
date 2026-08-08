"""频控阈值与封禁管理路由。

补齐 V2 的一处链路缺口：``fangyu:clock:limits:{site_id}`` 此前只有 gateway 侧
读取方、没有写入方，导致站点级阈值永远走默认值。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.clock.windows import ALL_WINDOWS, ClockDimension
from fangyu_shared.schemas.clock import ClockLimits
from fangyu_shared.schemas.common import SuccessResponse
from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.services.clock_service import ClockService
from src.interfaces.http.dependencies import get_clock_service, require_permission

from .schemas import ClockBanRequest, ClockLimitsUpdateRequest

router = APIRouter(prefix="/sites/{site_id}/clock", tags=["clock"])
global_router = APIRouter(prefix="/clock", tags=["clock"])


@router.get(
    "/limits",
    response_model=SuccessResponse[ClockLimits],
    dependencies=[Depends(require_permission("clock.read"))],
)
async def get_limits(
    site_id: int,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[ClockLimits]:
    """读取阈值。未配置时返回默认值，与网关的回退行为一致。"""
    return SuccessResponse(data=await service.get_limits(site_id))


@router.get(
    "/windows",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("clock.read"))],
)
async def list_windows() -> SuccessResponse[list[dict[str, Any]]]:
    """列出可配置的窗口及其真实宽度。

    前端据此渲染表单，避免把窗口名写死在两处——V1 就出现过
    ``BUCKET_60S_WINDOW = 180`` 这类名实不符。
    """
    return SuccessResponse(
        data=[{"name": w.name, "seconds": w.seconds} for w in ALL_WINDOWS]
    )


@router.put(
    "/limits",
    response_model=SuccessResponse[ClockLimits],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def put_limits(
    site_id: int,
    payload: ClockLimitsUpdateRequest,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[ClockLimits]:
    """更新阈值。未知窗口名或负阈值会被 400 拒绝。"""
    try:
        limits = await service.put_limits(
            site_id,
            enabled=payload.enabled,
            windows=payload.windows,
            ban_seconds=payload.ban_seconds,
            ban_enabled=payload.ban_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(data=limits)


@router.delete(
    "/limits",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def reset_limits(
    site_id: int,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, bool]]:
    """清除自定义阈值，回退默认值。"""
    deleted = await service.reset_limits(site_id)
    return SuccessResponse(data={"deleted": deleted})


@router.post(
    "/bans",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def create_ban(
    site_id: int,
    payload: ClockBanRequest,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, Any]]:
    """手工封禁某个 IP 或指纹。"""
    return SuccessResponse(
        data=await service.ban(
            site_id,
            payload.dimension,
            payload.value,
            seconds=payload.seconds,
            reason=payload.reason,
        )
    )


@router.get(
    "/bans",
    response_model=SuccessResponse[dict[str, Any] | None],
    dependencies=[Depends(require_permission("clock.read"))],
)
async def get_ban(
    site_id: int,
    dimension: ClockDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, Any] | None]:
    """查询封禁状态与剩余时长。未封禁返回 data=null。"""
    return SuccessResponse(data=await service.get_ban(site_id, dimension, value))


@router.delete(
    "/bans",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def delete_ban(
    site_id: int,
    dimension: ClockDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, bool]]:
    """解封。"""
    removed = await service.unban(site_id, dimension, value)
    return SuccessResponse(data={"removed": removed})


@router.post(
    "/limits/resync",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def resync(
    site_id: int,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, int]]:
    """把库里全部阈值重推 Redis，用于 Redis flush 后恢复。"""
    return SuccessResponse(data=await service.resync_all())


# ── 全局频控（site_id=0）────────────────────────────────────────────────

_GLOBAL_SITE = 0


@global_router.get(
    "/limits",
    response_model=SuccessResponse[ClockLimits],
    dependencies=[Depends(require_permission("clock.read"))],
)
async def get_global_limits(
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[ClockLimits]:
    return SuccessResponse(data=await service.get_limits(_GLOBAL_SITE))


@global_router.get(
    "/windows",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("clock.read"))],
)
async def list_global_windows() -> SuccessResponse[list[dict[str, Any]]]:
    return SuccessResponse(
        data=[{"name": w.name, "seconds": w.seconds} for w in ALL_WINDOWS]
    )


@global_router.put(
    "/limits",
    response_model=SuccessResponse[ClockLimits],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def put_global_limits(
    payload: ClockLimitsUpdateRequest,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[ClockLimits]:
    try:
        limits = await service.put_limits(
            _GLOBAL_SITE,
            enabled=payload.enabled,
            windows=payload.windows,
            ban_seconds=payload.ban_seconds,
            ban_enabled=payload.ban_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(data=limits)


@global_router.delete(
    "/limits",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def reset_global_limits(
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, bool]]:
    deleted = await service.reset_limits(_GLOBAL_SITE)
    return SuccessResponse(data={"deleted": deleted})


@global_router.post(
    "/bans",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def create_global_ban(
    payload: ClockBanRequest,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, Any]]:
    return SuccessResponse(
        data=await service.ban(
            _GLOBAL_SITE,
            payload.dimension,
            payload.value,
            seconds=payload.seconds,
            reason=payload.reason,
        )
    )


@global_router.get(
    "/bans",
    response_model=SuccessResponse[dict[str, Any] | None],
    dependencies=[Depends(require_permission("clock.read"))],
)
async def get_global_ban(
    dimension: ClockDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, Any] | None]:
    return SuccessResponse(data=await service.get_ban(_GLOBAL_SITE, dimension, value))


@global_router.delete(
    "/bans",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def delete_global_ban(
    dimension: ClockDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, bool]]:
    removed = await service.unban(_GLOBAL_SITE, dimension, value)
    return SuccessResponse(data={"removed": removed})


@global_router.post(
    "/limits/resync",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("clock.write"))],
)
async def resync_global(
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, int]]:
    return SuccessResponse(data=await service.resync_all())

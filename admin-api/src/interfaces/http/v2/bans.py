"""封禁查询与人工解除。

补齐 V2 的运维缺口：封禁此前只有 gateway 侧的自动写入（频控超限升级）与
``clock.py`` 里的点查/点删，**没有列表入口**。误封时运维必须先知道被封的
确切值才能解封，而 IP 维度存的是 ``sha256_hex(ip)[:32]``——从访客的投诉里
根本推不出来。没有列表页，实际唯一的处理办法是等封禁 TTL 自然过期。

与 ``clock.py`` 中已有 ban 端点的关系
------------------------------------
``clock.py`` 保留原有的 ``POST/GET/DELETE /apps/{id}/clock/bans``，本模块是
独立前缀 ``/apps/{id}/bans``，提供列表与批量解除。刻意不动 clock 侧的端点：
它们已在用，挪走会破坏调用方。两处都委托同一个 ``ClockService``，不存在
第二套封禁逻辑。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.clock.windows import ClockDimension
from fangyu_shared.schemas.common import SuccessResponse
from fastapi import APIRouter, Depends, Query

from src.application.services.clock_service import ClockService
from src.interfaces.http.dependencies import get_clock_service, require_permission

from .schemas import BanUnbanBatchRequest

router = APIRouter(prefix="/sites/{site_id}/bans", tags=["bans"])


@router.get(
    "",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("clock.read"))],
    summary="游标翻页列出封禁",
)
async def list_bans(
    site_id: int,
    dimension: ClockDimension | None = Query(
        default=None, description="按维度过滤；不传则两个维度都列"
    ),
    cursor: int = Query(default=0, ge=0, description="上一页返回的 nextCursor，首页传 0"),
    count: int = Query(default=200, ge=1, le=1000, description="单批扫描键数（近似值）"),
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, Any]]:
    """列出封禁及剩余 TTL。"""
    return SuccessResponse(
        data=await service.list_bans(
            site_id, dimension=dimension, cursor=cursor, count=count
        )
    )


@router.delete(
    "",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
    summary="解除单条封禁",
)
async def delete_ban(
    site_id: int,
    dimension: ClockDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, bool]]:
    """解封一条。``removed=false`` 表示本就没有这条封禁。"""
    removed = await service.unban(site_id, dimension, value)
    return SuccessResponse(data={"removed": removed})


@router.post(
    "/batch-unban",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("clock.write"))],
    summary="批量解除封禁",
)
async def batch_unban(
    site_id: int,
    payload: BanUnbanBatchRequest,
    service: ClockService = Depends(get_clock_service),
) -> SuccessResponse[dict[str, int]]:
    """批量解封。"""
    items = [(item.dimension, item.value) for item in payload.items]
    return SuccessResponse(data=await service.unban_many(site_id, items))

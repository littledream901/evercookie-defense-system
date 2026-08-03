"""app 级 IP/指纹白名单。

白名单命中时 gateway 在流水线**最前面**直接放行，跳过频控、威胁情报、安全
检查与评分。这是误封唯一的即时解除手段：被频控封禁的访客连 SecurityChecker
都到不了，只清理封禁键的话，下一个请求可能又触发一次封禁。

权限口径
--------
复用 ``clock.read`` / ``clock.write``，不新增权限码。理由是运维语义相同——
「谁能改封禁，谁就能改白名单」；拆成两套权限会出现「能解封但不能加白名单」
这种半残状态，反而增加误封处置的门槛。
"""

from __future__ import annotations

from typing import Any

from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.whitelist.keys import WhitelistDimension
from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.services.whitelist_service import (
    WhitelistError,
    WhitelistService,
)
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_whitelist_service,
    require_permission,
)

from .schemas import WhitelistAddRequest

router = APIRouter(prefix="/sites/{site_id}/whitelist", tags=["whitelist"])
global_router = APIRouter(prefix="/whitelist", tags=["whitelist"])


@router.get(
    "",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("clock.read"))],
    summary="列出白名单",
)
async def list_whitelist(
    site_id: int,
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """列出某 app 的全部白名单条目。

    不分页：条数受 ``MAX_ENTRIES_PER_APP`` 约束，一次取回比游标翻页更适合
    人工核对——白名单最常见的操作是「通读一遍看还有哪条不该留着」。
    """
    return SuccessResponse(data=await service.list_entries(site_id))


@router.post(
    "",
    response_model=SuccessResponse[dict[str, Any]],
    status_code=201,
    dependencies=[Depends(require_permission("clock.write"))],
    summary="新增白名单条目",
)
async def add_whitelist(
    site_id: int,
    payload: WhitelistAddRequest,
    user_id: int = Depends(get_current_user_id),
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[dict[str, Any]]:
    """新增或覆盖一条白名单。

    ``dimension=ip`` 时 ``value`` 是**明文 IP**，与封禁的哈希口径相反——
    白名单靠人工录入，要求先算哈希等于废掉这个功能。IP 会被规范化成压缩
    表示后存储，保证与 gateway 侧 ``str(ctx.ip)`` 的查表键一致。

    重复提交同一个值不报错，视为更新备注。
    """
    try:
        entry = await service.add(
            site_id,
            payload.dimension,
            payload.value,
            note=payload.note,
            created_by=str(user_id),
        )
    except WhitelistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(data=entry)


@router.delete(
    "",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
    summary="删除白名单条目",
)
async def remove_whitelist(
    site_id: int,
    dimension: WhitelistDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[dict[str, bool]]:
    """删除一条。``removed=false`` 表示本就不存在。

    删除立即生效：白名单产出的 allow 不写决策缓存（见
    ``DecidedBy.is_time_sensitive``），不存在「删了还能放行一个 TTL」的窗口。
    """
    try:
        removed = await service.remove(site_id, dimension, value)
    except WhitelistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(data={"removed": removed})


@router.delete(
    "/all",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("clock.write"))],
    summary="清空白名单",
)
async def clear_whitelist(
    site_id: int,
    confirm: bool = Query(
        default=False, description="必须显式传 true，防止误调用清空准入清单"
    ),
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[dict[str, int]]:
    """清空某 app 的白名单。"""
    if not confirm:
        raise HTTPException(status_code=400, detail="清空白名单需显式传 confirm=true")
    return SuccessResponse(data={"removed": await service.clear(site_id)})


# ── 全局白名单（site_id=0）──────────────────────────────────────────────

_GLOBAL_SITE = 0


@global_router.get(
    "",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("clock.read"))],
    summary="全局白名单列表",
)
async def list_global_whitelist(
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    return SuccessResponse(data=await service.list_entries(_GLOBAL_SITE))


@global_router.post(
    "",
    response_model=SuccessResponse[dict[str, Any]],
    status_code=201,
    dependencies=[Depends(require_permission("clock.write"))],
    summary="新增全局白名单条目",
)
async def add_global_whitelist(
    payload: WhitelistAddRequest,
    user_id: int = Depends(get_current_user_id),
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[dict[str, Any]]:
    try:
        entry = await service.add(
            _GLOBAL_SITE, payload.dimension, payload.value,
            note=payload.note, created_by=str(user_id),
        )
    except WhitelistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(data=entry)


@global_router.delete(
    "",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("clock.write"))],
    summary="删除全局白名单条目",
)
async def remove_global_whitelist(
    dimension: WhitelistDimension = Query(...),
    value: str = Query(..., min_length=1, max_length=128),
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[dict[str, bool]]:
    try:
        removed = await service.remove(_GLOBAL_SITE, dimension, value)
    except WhitelistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(data={"removed": removed})


@global_router.delete(
    "/all",
    response_model=SuccessResponse[dict[str, int]],
    dependencies=[Depends(require_permission("clock.write"))],
    summary="清空全局白名单",
)
async def clear_global_whitelist(
    confirm: bool = Query(default=False),
    service: WhitelistService = Depends(get_whitelist_service),
) -> SuccessResponse[dict[str, int]]:
    if not confirm:
        raise HTTPException(status_code=400, detail="清空白名单需显式传 confirm=true")
    return SuccessResponse(data={"removed": await service.clear(_GLOBAL_SITE)})

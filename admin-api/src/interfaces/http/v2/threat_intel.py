"""威胁情报管理 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from src.application.services.threat_intel_service import ThreatIntelService
from src.interfaces.http.dependencies import (
    get_threat_intel_service,
    get_current_user_id,
    require_permission,
)

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])


@router.get("", summary="分页查询威胁情报")
async def list_threat_intel(
    category: str | None = Query(None),
    source: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.read")),
) -> dict[str, Any]:
    return await svc.list_active(
        category=category,
        source=source,
        page=page,
        page_size=page_size,
    )


@router.post("", summary="新增/更新一条情报", status_code=status.HTTP_201_CREATED)
async def add_threat_intel(
    body: dict[str, Any] = Body(...),
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> dict[str, Any]:
    ip = body.get("ip", "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip 不能为空")
    expires_at: datetime | None = None
    if raw_exp := body.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(raw_exp)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="expires_at 格式错误，请使用 ISO 8601")
    return await svc.add(
        ip,
        category=body.get("category", "malicious"),
        severity=body.get("severity", "medium"),
        source=body.get("source", "manual"),
        confidence=int(body.get("confidence", 80)),
        description=body.get("description", ""),
        expires_at=expires_at,
        extra=body.get("extra"),
    )


@router.delete("/{ip:path}", summary="停用一条情报")
async def remove_threat_intel(
    ip: str,
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> dict[str, Any]:
    deactivated = await svc.remove(ip)
    if not deactivated:
        raise HTTPException(status_code=404, detail=f"IP {ip!r} 不存在或已停用")
    return {"ok": True, "ip": ip}


@router.post("/bulk-import", summary="批量导入情报（JSON 数组）")
async def bulk_import(
    records: list[dict[str, Any]] = Body(...),
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> dict[str, int]:
    if not records:
        raise HTTPException(status_code=400, detail="records 不能为空")
    for rec in records:
        if not rec.get("ip"):
            raise HTTPException(status_code=400, detail="每条记录都必须包含 ip 字段")
    return await svc.bulk_import(records)


@router.post("/sync-redis", summary="将 DB 全量同步到 Redis")
async def sync_redis(
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> dict[str, Any]:
    return await svc.sync_to_redis()


@router.get("/stats/redis", summary="Redis 命中统计")
async def redis_stats(
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    return await svc.redis_stats()

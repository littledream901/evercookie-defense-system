"""威胁情报管理 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fangyu_shared.schemas.common import SuccessResponse
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from src.application.services.reputation_sync_service import ReputationSyncService
from src.application.services.threat_intel_service import ThreatIntelService
from src.interfaces.http.dependencies import (
    get_reputation_sync_service,
    get_threat_intel_service,
    get_current_user_id,
    require_permission,
)

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])


@router.get("", summary="分页查询威胁情报", response_model=SuccessResponse[dict[str, Any]])
async def list_threat_intel(
    category: str | None = Query(None),
    source: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.read")),
) -> SuccessResponse[dict[str, Any]]:
    data = await svc.list_active(
        category=category,
        source=source,
        severity=severity,
        page=page,
        page_size=page_size,
    )
    return SuccessResponse(data=data)


@router.post("", summary="新增/更新一条情报", status_code=status.HTTP_201_CREATED, response_model=SuccessResponse[dict[str, Any]])
async def add_threat_intel(
    body: dict[str, Any] = Body(...),
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> SuccessResponse[dict[str, Any]]:
    ip = body.get("ip", "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip 不能为空")
    expires_at: datetime | None = None
    if raw_exp := body.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(raw_exp)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="expires_at 格式错误，请使用 ISO 8601")
    data = await svc.add(
        ip,
        category=body.get("category", "malicious"),
        severity=body.get("severity", "medium"),
        source=body.get("source", "manual"),
        confidence=int(body.get("confidence", 80)),
        description=body.get("description", ""),
        expires_at=expires_at,
        extra=body.get("extra"),
    )
    return SuccessResponse(data=data)


@router.delete("/{ip:path}", summary="停用一条情报", response_model=SuccessResponse[dict[str, Any]])
async def remove_threat_intel(
    ip: str,
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> SuccessResponse[dict[str, Any]]:
    deactivated = await svc.remove(ip)
    if not deactivated:
        raise HTTPException(status_code=404, detail=f"IP {ip!r} 不存在或已停用")
    return SuccessResponse(data={"ok": True, "ip": ip})


@router.post("/bulk-import", summary="批量导入情报（JSON 数组）", response_model=SuccessResponse[dict[str, int]])
async def bulk_import(
    records: list[dict[str, Any]] = Body(...),
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> SuccessResponse[dict[str, int]]:
    if not records:
        raise HTTPException(status_code=400, detail="records 不能为空")
    for rec in records:
        if not rec.get("ip"):
            raise HTTPException(status_code=400, detail="每条记录都必须包含 ip 字段")
    return SuccessResponse(data=await svc.bulk_import(records))


@router.post("/sync-redis", summary="将 DB 全量同步到 Redis", response_model=SuccessResponse[dict[str, Any]])
async def sync_redis(
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> SuccessResponse[dict[str, Any]]:
    return SuccessResponse(data=await svc.sync_to_redis())


@router.post("/sync", summary="手动触发声誉回流（ClickHouse MV → Redis ProfileCache）", response_model=SuccessResponse[dict[str, Any]])
async def sync_reputation(
    svc: ReputationSyncService = Depends(get_reputation_sync_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> SuccessResponse[dict[str, Any]]:
    """从 ClickHouse mv_ip_reputation_daily / mv_fingerprint_reputation_daily 读取聚合，
    计算声誉分并写回 Redis ProfileCache，同时把高风险 IP 沉淀进情报库。

    周期执行归 worker（数据面常驻进程），admin 不再注册同名定时任务；此端点
    供管理员随时手动强制同步一次，逻辑与 worker 共用
    :mod:`fangyu_shared.reputation`。
    """
    result = await svc.sync()
    return SuccessResponse(data=result.to_dict())


@router.post("/sync-external", summary="手动触发外部情报源拉取（Tor/URLhaus/AbuseIPDB）", response_model=SuccessResponse[dict[str, Any]])
async def sync_external_intel(
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.write")),
) -> SuccessResponse[dict[str, Any]]:
    """从外部情报源（Tor 出口节点、URLhaus、AbuseIPDB）拉取最新情报，
    写入 DB 后同步到 Redis。定时任务每 6 小时自动执行；此端点供手动触发。
    """
    from src.infrastructure.external_intel_fetcher import ExternalIntelFetcher
    fetcher = ExternalIntelFetcher()
    entries = await fetcher.fetch_all()
    result = await svc.bulk_import([
        {
            "ip": e["ip"],
            "category": e["category"],
            "severity": e.get("severity", "medium"),
            "source": e["source"],
            "confidence": e.get("confidence", 80),
            "description": e.get("description", ""),
        }
        for e in entries
    ])
    await svc.sync_to_redis()
    return SuccessResponse(data={**result, "sources": ["tor_project", "urlhaus", "abuseipdb"]})


@router.get("/external-sources", summary="查询外部情报源配置状态", response_model=SuccessResponse[dict[str, Any]])
async def get_external_sources(
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.read")),
) -> SuccessResponse[dict[str, Any]]:
    """返回各外部情报源的配置状态与当前贡献条目数。

    ``entry_count`` 取自 ``biz_threat_intel`` 按 source 的分组统计，口径与列表
    一致（排除已过期条目）。额外返回 ``manual`` 伪源，让「手工录入 vs 外部拉取」
    的构成在同一张卡片里可比。
    """
    import os

    counts = await svc.count_by_source()
    has_key = bool(os.getenv("ABUSEIPDB_API_KEY"))

    return SuccessResponse(data={
        "sources": [
            {
                "id": "tor_project",
                "name": "Tor Project",
                "url": "https://check.torproject.org/torbulkexitlist",
                "enabled": True,
                "requiresApiKey": False,
                "entry_count": counts.get("tor_project", 0),
                "description": "Tor 出口节点列表，更新频率约每小时",
            },
            {
                "id": "urlhaus",
                "name": "URLhaus (abuse.ch)",
                "url": "https://urlhaus.abuse.ch/downloads/csv_recent/",
                "enabled": True,
                "requiresApiKey": False,
                "entry_count": counts.get("urlhaus", 0),
                "description": "恶意 URL 主机 IP，实时更新",
            },
            {
                "id": "abuseipdb",
                "name": "AbuseIPDB",
                "url": "https://api.abuseipdb.com/api/v2/blacklist",
                "enabled": has_key,
                "requiresApiKey": True,
                "configured": has_key,
                "entry_count": counts.get("abuseipdb", 0),
                "description": "社区举报黑名单，需要 API Key（环境变量 ABUSEIPDB_API_KEY）",
            },
            {
                "id": "manual",
                "name": "手工录入 / 导入",
                "url": "",
                "enabled": True,
                "requiresApiKey": False,
                "entry_count": counts.get("manual", 0) + counts.get("import", 0),
                "description": "通过页面新增或 JSON 批量导入的条目",
            },
        ]
    })


@router.get("/stats/redis", summary="Redis 命中统计", response_model=SuccessResponse[dict[str, Any]])
async def redis_stats(
    svc: ThreatIntelService = Depends(get_threat_intel_service),
    _: int = Depends(require_permission("threat_intel.read")),
) -> SuccessResponse[dict[str, Any]]:
    return SuccessResponse(data=await svc.redis_stats())

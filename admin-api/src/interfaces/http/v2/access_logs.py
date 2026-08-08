"""访问日志查询路由。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from fangyu_shared.clickhouse_manager import ClickHouseClient, get_clickhouse
from fangyu_shared.schemas.common import PageResponse, SuccessResponse

from src.infrastructure.clickhouse.access_log_query import AccessLogQueryService
from src.interfaces.http.dependencies import require_permission

router = APIRouter(prefix="/access-logs", tags=["access-logs"])

# ClickHouse 列名 → 前端字段名映射
_FIELD_MAP = {
    "os_name": "os",
    "browser_name": "browser",
    "decided_stage": "stage",
    "decided_rule_id": "rule_id",
    "device_id": "device_id",  # keep
}


def _transform_row(row: dict) -> dict:
    """将 ClickHouse 原始列名转换为前端期望的字段名，并统一类型。"""
    if not row:
        return row
    # 字段重命名
    for ch_name, api_name in _FIELD_MAP.items():
        if ch_name in row and ch_name != api_name:
            row[api_name] = row.pop(ch_name)
    # UInt8(0/1) → bool
    for col in ("is_bot", "evercookie_restore", "is_vpn", "is_proxy"):
        if col in row and not isinstance(row[col], bool):
            row[col] = bool(row[col])
    # 添加 is_crawler 字段（基于 crawler_name 或 crawler_category 是否存在）
    if "is_crawler" not in row:
        row["is_crawler"] = bool(row.get("crawler_name") or row.get("crawler_category"))
    return row


def _transform_rows(rows: list[dict]) -> list[dict]:
    return [_transform_row(r) for r in rows]


def _service(client: ClickHouseClient = Depends(get_clickhouse)) -> AccessLogQueryService:
    return AccessLogQueryService(client)


@router.get(
    "/stats/summary",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def access_log_stats(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """访问日志统计摘要。
    
    Args:
        site_id: 站点ID，对应 ClickHouse 的 app_id 列（
    
    Note:
        ClickHouse 的 app_id 列实际存储的是 site_id（
        应用级聚合查询需要在上层实现
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    return SuccessResponse(
        data=await service.stats(
            site_id=site_id,
            start=actual_start,
            end=actual_end
        )
    )


@router.get(
    "",
    response_model=SuccessResponse[PageResponse[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def list_access_logs(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    request_id: str | None = Query(default=None, alias="requestId"),
    ip: str | None = None,
    fingerprint: str | None = None,
    verdict: str | None = None,
    mechanism: str | None = None,
    decided_by: str | None = Query(default=None, alias="decidedBy"),
    country: str | None = None,
    device_type: str | None = Query(default=None, alias="deviceType"),
    crawler_name: str | None = Query(default=None, alias="crawlerName"),
    crawler_category: str | None = Query(default=None, alias="crawlerCategory"),
    crawler_vendor: str | None = Query(default=None, alias="crawlerVendor"),
    connection_type: str | None = Query(default=None, alias="connectionType"),
    path: str | None = None,
    is_bot: bool | None = Query(default=None, alias="isBot"),
    is_crawler: bool | None = Query(default=None, alias="isCrawler"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500, alias="pageSize"),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[PageResponse[dict[str, Any]]]:
    """访问日志列表（分页）。
    
    Args:
        site_id: 站点ID，对应 ClickHouse 的 app_id 列（
    
    Note:
        ClickHouse 的 app_id 列实际存储的是 site_id（
        应用级聚合查询需要在上层实现（先查询应用下的站点列表，然后分别查询）
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows, total = await service.list_paged(
        site_id=site_id,
        start=actual_start,
        end=actual_end,
        filters={
            "request_id": request_id or "",
            "ip": ip or "",
            "fingerprint": fingerprint or "",
            "verdict": verdict or "",
            "mechanism": mechanism or "",
            "decided_by": decided_by or "",
            "country": country or "",
            "device_type": device_type or "",
            "crawler_name": crawler_name or "",
            "crawler_category": crawler_category or "",
            "crawler_vendor": crawler_vendor or "",
            "connection_type": connection_type or "",
            "path": path or "",
        },
        is_bot=is_bot,
        is_crawler=is_crawler,
        page=page,
        page_size=page_size,
    )
    return SuccessResponse(data=PageResponse(items=_transform_rows(rows), total=total, page=page, pageSize=page_size))


@router.get(
    "/{request_id}",
    response_model=SuccessResponse[dict[str, Any] | None],
    dependencies=[Depends(require_permission("analytics.read"))],
)
async def get_access_log(
    request_id: str,
    site_id: int | None = Query(default=None, alias="siteId"),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[dict[str, Any] | None]:
    row = await service.get_by_request_id(app_id=site_id, request_id=request_id)
    return SuccessResponse(data=_transform_row(row) if row else None)


@router.get(
    "/{request_id}/traces",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="规则条件命中明细（TTL 7 天）",
)
async def get_access_log_traces(
    request_id: str,
    site_id: int | None = Query(default=None, alias="siteId"),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """返回该请求的规则条件逐条命中情况。

    存储在冷表 ``fangyu.decision_traces``，TTL 7 天，超期后查询返回空列表。
    """
    rows = await service.get_traces(app_id=site_id, request_id=request_id)
    return SuccessResponse(data=rows)


@router.get(
    "/shadow/impact",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="影子规则影响面分析",
)
async def shadow_impact(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """统计各草稿影子规则在历史流量上的命中量，用于发布前评估拦截面。

    返回格式：``[{shadow_rule_id, would_hit_count, currently_passed_count}]``
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows = await service.shadow_impact(app_id=site_id, start=actual_start, end=actual_end)
    return SuccessResponse(data=rows)


@router.get(
    "/pool/distribution",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="地址池命中分布",
)
async def pool_distribution(
    site_id: int = Query(alias="siteId"),
    rule_id: int | None = Query(default=None, alias="ruleId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """轮询地址池近期命中分布，验证权重配置是否生效。

    返回格式：``[{target_url, hit_count, error_count, first_hit_at, last_hit_at}]``

    - rule_id 可选，不传时按 app 汇总（多条规则各有地址池时汇总没有意义）
    - 默认查询近 24 小时
    - 只统计 target_kind='url_pool' 的记录，排除单地址跳转噪音
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows = await service.pool_distribution(
        app_id=site_id, start=actual_start, end=actual_end, rule_id=rule_id
    )
    return SuccessResponse(data=rows)


@router.get(
    "/crawler/overview",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="爬虫流量概览",
)
async def crawler_overview(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[dict[str, Any]]:
    """爬虫流量概览统计。
    
    返回：总请求数、爬虫请求数、非爬虫请求数、唯一爬虫数、恶意爬虫请求数
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    data = await service.crawler_overview(app_id=site_id, start=actual_start, end=actual_end)
    return SuccessResponse(data=data)


@router.get(
    "/crawler/vendor-distribution",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="爬虫厂商分布",
)
async def crawler_vendor_distribution(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """按爬虫厂商统计请求分布。
    
    返回：厂商名称、请求数、爬虫类型数、各裁决类型统计
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows = await service.crawler_vendor_distribution(app_id=site_id, start=actual_start, end=actual_end)
    return SuccessResponse(data=rows)


@router.get(
    "/crawler/category-distribution",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="爬虫分类分布",
)
async def crawler_category_distribution(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """按爬虫分类统计请求分布。
    
    返回：分类名称、请求数、爬虫类型数、恶意请求数、平均处理时间
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows = await service.crawler_category_distribution(app_id=site_id, start=actual_start, end=actual_end)
    return SuccessResponse(data=rows)


@router.get(
    "/crawler/top-list",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="爬虫访问频率Top排行",
)
async def crawler_top_list(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """爬虫访问频率Top排行。
    
    返回：爬虫名称、厂商、分类、请求数、唯一IP数、被拦截数、首次/最后访问时间
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows = await service.crawler_top_list(app_id=site_id, start=actual_start, end=actual_end, limit=limit)
    return SuccessResponse(data=rows)


@router.get(
    "/crawler/timeline",
    response_model=SuccessResponse[list[dict[str, Any]]],
    dependencies=[Depends(require_permission("analytics.read"))],
    summary="爬虫流量时间趋势",
)
async def crawler_timeline(
    site_id: int | None = Query(default=None, alias="siteId"),
    start: datetime | None = None,
    end: datetime | None = None,
    granularity: str = Query(default="hour", regex="^(minute|hour|day)$"),
    service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[list[dict[str, Any]]]:
    """爬虫流量时间趋势（分爬虫/非爬虫）。
    
    返回：时间桶、爬虫数量、非爬虫数量、总数量
    """
    actual_end = end or datetime.utcnow()
    actual_start = start or actual_end - timedelta(days=1)
    rows = await service.crawler_timeline(
        app_id=site_id, start=actual_start, end=actual_end, granularity=granularity
    )
    return SuccessResponse(data=rows)

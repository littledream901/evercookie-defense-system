"""威胁情报管理端路由。

五种情报类型（asn / crawler / fingerprint / geo_ip / ip_profile）
共用一套 CRUD，类型以路径段传入，与前端 ``INTEL_BASE = '/api/v2/intelligence'``
的契约对齐。
"""

from __future__ import annotations

import csv
import io
from typing import Annotated, Any

from fangyu_shared.schemas.common import SuccessResponse
from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.responses import StreamingResponse

from src.application.services.intel_service import IntelService
from src.infrastructure.repositories.intel_repository import IntelType
from src.interfaces.http.dependencies import get_intel_service, require_permission

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# 各类型允许的精确过滤字段，避免前端任意透传参数打到 SQL 上
_FILTERABLE: dict[IntelType, set[str]] = {
    IntelType.asn: {"network_type"},
    IntelType.crawler: {"crawler_category", "feature_type", "is_legitimate"},
    IntelType.fingerprint: {"finger_type", "source"},
    IntelType.geo_ip: {"country"},
    IntelType.ip_profile: {"network_type", "is_vpn", "is_proxy", "is_tor"},
}

# 写入时允许的字段白名单（排除 id / 时间戳等由服务端维护的列）
_WRITABLE: dict[IntelType, set[str]] = {
    IntelType.asn: {
        "asn", "operator", "network_type", "country", "risk_score", "is_active", "note",
    },
    IntelType.crawler: {
        "feature_type", "pattern", "crawler_category", "crawler_name",
        "is_legitimate", "risk_score", "is_active", "note",
    },
    IntelType.fingerprint: {
        "finger_id", "finger_type", "risk_score", "source", "canvas_hash",
        "webgl_params", "audio_hash", "screen_info", "is_active", "note",
    },
    IntelType.geo_ip: {"cidr", "country", "region", "city", "is_active", "note"},
    IntelType.ip_profile: {
        "cidr", "network_type", "is_vpn", "is_proxy", "is_tor",
        "risk_score", "is_active", "note",
    },
}

_INT_FIELDS = {"asn", "risk_score", "hit_count"}
_BOOL_FIELDS = {"is_active", "is_legitimate", "is_vpn", "is_proxy", "is_tor"}


def _build_presets() -> dict[IntelType, dict[str, list[dict[str, Any]]]]:
    """从项目现有硬编码常量派生预设，避免另造一份数据。

    ASN 取自 gateway 的 ``_DATACENTER_ASNS`` / ``_MOBILE_ASNS``，爬虫特征取自
    shared 的 ``CRAWLER_SIGNATURES``，保证预设与决策链路的既有认定一致。
    """
    from fangyu_shared.intel import DATACENTER_ASNS, MOBILE_ASNS
    from fangyu_shared.ua.crawlers import CRAWLER_SIGNATURES

    datacenter = [
        {"asn": a, "network_type": "DATACENTER", "risk_score": 45, "note": "预设：数据中心"}
        for a in sorted(DATACENTER_ASNS)
    ]
    mobile = [
        {"asn": a, "network_type": "MOBILE", "risk_score": 5, "note": "预设：移动网络"}
        for a in sorted(MOBILE_ASNS)
    ]

    # 正规爬虫（搜索引擎/社交预览）默认不计分，其余按类别给基础分
    # 类别名必须与 CRAWLER_CATEGORIES 一致：社交类是 "social" 而非 "social_media"
    _legit = {"search_engine", "social"}
    _scores = {"security": 60, "ai_crawler": 25, "seo": 30, "archive": 20}

    crawlers: list[dict[str, Any]] = []
    for sig in CRAWLER_SIGNATURES:
        legitimate = sig.category in _legit
        crawlers.append({
            "feature_type": "user_agent",
            "pattern": sig.pattern.pattern,
            "crawler_category": sig.category,
            "crawler_name": sig.vendor,
            "is_legitimate": legitimate,
            "risk_score": 0 if legitimate else _scores.get(sig.category, 15),
            "note": "预设：内置爬虫签名",
        })

    return {
        IntelType.asn: {
            "datacenter": datacenter,
            "mobile": mobile,
            "all": datacenter + mobile,
        },
        IntelType.crawler: {"builtin": crawlers},
    }


# 预设的展示文案。与 _build_presets() 产出的 key 一一对应，前端不再自带一份
_PRESET_LABELS: dict[str, str] = {
    "datacenter": "主流数据中心 ASN",
    "mobile": "移动网络 ASN",
    "all": "全部内置 ASN",
    "builtin": "内置爬虫签名",
}

_PRESET_DESCS: dict[str, str] = {
    "datacenter": "覆盖 AWS/Azure/GCP/阿里云/腾讯云等常见数据中心 ASN，风险分 45",
    "mobile": "三大运营商及主流移动网络 ASN，风险分 5",
    "all": "数据中心 + 移动网络的合集",
    "builtin": "搜索引擎/社交预览/安全扫描器等内置 UA 签名，正规爬虫不计分",
}


_PRESETS: dict[IntelType, dict[str, list[dict[str, Any]]]] = {}


def _presets() -> dict[IntelType, dict[str, list[dict[str, Any]]]]:
    global _PRESETS
    if not _PRESETS:
        _PRESETS = _build_presets()
    return _PRESETS


def _coerce(intel_type: IntelType, raw: dict[str, Any]) -> dict[str, Any]:
    """按白名单裁剪并做类型归一。

    CSV 导入与 JSON 提交共用此函数，前者所有值都是字符串，需转换。
    crawler 类型额外校验 pattern 是否为合法正则，非法 pattern 抛 ValueError
    而非静默写入，避免写入 DB 后 gateway 侧 30s 缓存刷新时静默跳过导致情报失效。
    """
    import re as _re

    allowed = _WRITABLE[intel_type]
    data: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in allowed or value is None or value == "":
            continue
        if key in _INT_FIELDS:
            data[key] = int(value)
        elif key in _BOOL_FIELDS:
            data[key] = (
                value if isinstance(value, bool)
                else str(value).strip().lower() in ("1", "true", "yes")
            )
        else:
            data[key] = str(value)

    # M-04：crawler pattern 必须是合法正则，否则 gateway 侧会静默跳过
    if intel_type == IntelType.crawler and "pattern" in data:
        try:
            _re.compile(data["pattern"])
        except _re.error as exc:
            raise ValueError(f"crawler pattern 不是合法正则：{exc}") from exc

    return data


# ── overview ───────────────────────────────────────────────────────────────
# 必须注册在 /{intel_type} 之前，否则 "overview" 会被当作类型段匹配


@router.get(
    "/overview",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.read"))],
    summary="情报总览统计",
)
async def get_overview(
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    return SuccessResponse(data=await service.overview())


# ── 数据来源 ────────────────────────────────────────────────────────────────
# 同样必须注册在 /{intel_type} 之前


@router.get(
    "/{intel_type}/presets",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.read"))],
    summary="该类型可用的内置预设数据源",
)
async def list_intel_presets(
    intel_type: Annotated[IntelType, Path()],
) -> SuccessResponse[dict[str, Any]]:
    """返回该情报类型的内置预设列表及各自可载入条数。

    预设名由后端单一来源产出，前端据此渲染，避免两处各自硬编码导致
    载入时 404。``entry_count`` 是预设自带条数，不代表已入库条数。
    """
    presets = _presets().get(intel_type, {})
    return SuccessResponse(data={
        "sources": [
            {
                "name": name,
                "label": _PRESET_LABELS.get(name, name),
                "description": _PRESET_DESCS.get(name, ""),
                "entry_count": len(records),
            }
            for name, records in presets.items()
        ]
    })


@router.get(
    "/{intel_type}/external-sources",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.read"))],
    summary="该类型可用的外部情报源及贡献条目数",
)
async def list_intel_external_sources(
    intel_type: Annotated[IntelType, Path()],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    """返回该类型的 CIDR 外部源状态。

    目前仅 ip_profile 有外部源（云厂商官方网段清单），其余类型返回空列表，让
    前端可以无条件挂载卡片而不必按类型分支。``entry_count`` 依据 note 前缀统计，
    额外给出 ``manual`` 伪源以便对比手工录入与外部拉取的构成。
    """
    if intel_type is not IntelType.ip_profile:
        return SuccessResponse(data={"sources": []})

    from src.infrastructure.cidr_intel_fetcher import NOTE_PREFIX, SOURCES

    prefixes = [f"{NOTE_PREFIX}:{s.id}" for s in SOURCES]
    counts = await service.count_by_note_prefix(intel_type, prefixes)
    external_total = sum(counts.values())
    total = await service.count(intel_type)

    sources = [
        {**s.as_dict(), "entry_count": counts.get(f"{NOTE_PREFIX}:{s.id}", 0)} for s in SOURCES
    ]
    sources.append({
        "id": "manual",
        "name": "手工录入 / 导入",
        "url": "",
        "enabled": True,
        "requiresApiKey": False,
        "entry_count": max(total - external_total, 0),
        "description": "后台新增或 CSV 批量导入的条目",
    })
    return SuccessResponse(data={"sources": sources})


@router.post(
    "/{intel_type}/sync-external",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.write"))],
    summary="手动触发该类型的外部情报源拉取",
)
async def sync_intel_external_sources(
    intel_type: Annotated[IntelType, Path()],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    """拉取云厂商官方网段清单写入 IP 画像，并同步到 Redis。

    已存在的 cidr 会被跳过而非覆盖，避免冲掉运营的人工修正。
    """
    if intel_type is not IntelType.ip_profile:
        raise HTTPException(status_code=400, detail="该情报类型没有可用的外部数据源")

    from src.infrastructure.cidr_intel_fetcher import SOURCES, CidrIntelFetcher

    records = await CidrIntelFetcher().fetch_all()
    if not records:
        raise HTTPException(status_code=502, detail="外部数据源均拉取失败，请稍后重试")

    result = await service.bulk_import(intel_type, records)
    return SuccessResponse(data={**result, "sources": [s.id for s in SOURCES]})


# ── CRUD ───────────────────────────────────────────────────────────────────


@router.get(
    "/{intel_type}",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.read"))],
    summary="情报列表",
)
async def list_intel(
    intel_type: Annotated[IntelType, Path()],
    keyword: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    network_type: Annotated[str | None, Query()] = None,
    crawler_category: Annotated[str | None, Query()] = None,
    feature_type: Annotated[str | None, Query()] = None,
    finger_type: Annotated[str | None, Query()] = None,
    country: Annotated[str | None, Query()] = None,
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    candidates = {
        "network_type": network_type,
        "crawler_category": crawler_category,
        "feature_type": feature_type,
        "finger_type": finger_type,
        "country": country,
    }
    allowed = _FILTERABLE[intel_type]
    filters = {k: v for k, v in candidates.items() if k in allowed and v is not None}

    items, total = await service.list(
        intel_type, keyword=keyword, filters=filters, page=page, page_size=page_size
    )
    return SuccessResponse(
        data={"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.post(
    "/{intel_type}",
    response_model=SuccessResponse[dict[str, Any]],
    status_code=201,
    dependencies=[Depends(require_permission("threat_intel.write"))],
    summary="新增情报条目",
)
async def create_intel(
    intel_type: Annotated[IntelType, Path()],
    payload: dict[str, Any],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    try:
        data = _coerce(intel_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=400, detail="请求体缺少有效字段")
    return SuccessResponse(data=await service.create(intel_type, data))


@router.put(
    "/{intel_type}/{row_id}",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.write"))],
    summary="更新情报条目",
)
async def update_intel(
    intel_type: Annotated[IntelType, Path()],
    row_id: Annotated[int, Path(ge=1)],
    payload: dict[str, Any],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    try:
        data = _coerce(intel_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    updated = await service.update(intel_type, row_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="情报条目不存在")
    return SuccessResponse(data=updated)


@router.delete(
    "/{intel_type}/{row_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[Depends(require_permission("threat_intel.write"))],
    summary="删除情报条目",
)
async def delete_intel(
    intel_type: Annotated[IntelType, Path()],
    row_id: Annotated[int, Path(ge=1)],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, bool]]:
    ok = await service.delete(intel_type, row_id)
    if not ok:
        raise HTTPException(status_code=404, detail="情报条目不存在")
    return SuccessResponse(data={"ok": True})


# ── 导入 / 导出 / 预设 ──────────────────────────────────────────────────────


@router.post(
    "/{intel_type}/import",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.write"))],
    summary="CSV 批量导入",
)
async def import_intel_csv(
    intel_type: Annotated[IntelType, Path()],
    file: Annotated[UploadFile, File()],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV 需为 UTF-8 编码") from exc

    reader = csv.DictReader(io.StringIO(text))
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for lineno, row in enumerate(reader, start=2):
        try:
            data = _coerce(intel_type, row)
        except (TypeError, ValueError) as exc:
            errors.append(f"第 {lineno} 行：{exc}")
            continue
        if data:
            records.append(data)

    if not records:
        raise HTTPException(status_code=400, detail="CSV 中无有效数据行")

    result = await service.bulk_import(intel_type, records)
    if errors:
        result["errors"] = errors[:20]
    return SuccessResponse(data=result)


@router.get(
    "/{intel_type}/export",
    dependencies=[Depends(require_permission("threat_intel.read"))],
    summary="导出为 CSV",
)
async def export_intel_csv(
    intel_type: Annotated[IntelType, Path()],
    service: IntelService = Depends(get_intel_service),
) -> StreamingResponse:
    rows = await service.get_all_active(intel_type)
    fields = sorted(_WRITABLE[intel_type])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="intel_{intel_type.value}.csv"'
        },
    )


@router.post(
    "/{intel_type}/preset/{preset_name}",
    response_model=SuccessResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("threat_intel.write"))],
    summary="加载内置预设",
)
async def load_intel_preset(
    intel_type: Annotated[IntelType, Path()],
    preset_name: Annotated[str, Path()],
    service: IntelService = Depends(get_intel_service),
) -> SuccessResponse[dict[str, Any]]:
    presets = _presets().get(intel_type, {})
    records = presets.get(preset_name)
    if records is None:
        available = ", ".join(presets) or "无"
        raise HTTPException(
            status_code=404, detail=f"预设不存在，可用：{available}"
        )
    return SuccessResponse(data=await service.bulk_import(intel_type, list(records)))

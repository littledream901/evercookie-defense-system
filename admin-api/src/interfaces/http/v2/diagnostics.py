"""SDK / Adapter 接入诊断路由。

回答一个具体问题：这个站点的埋码到底接上了没有、接的是哪条路径、
以及实测接入方式与站点配置的 ``access_mode`` 是否一致。

诊断只读历史遥测（ClickHouse ``decision_events``），不向网关发探测请求，
因此不会产生真实决策事件、不消耗 nonce。

已知盲区（受现有链路限制，页面需如实告知，不能假装能诊断）：
验签失败的请求在网关中间件阶段就返回 401，从不进入事件流，
所以「密钥填错 / 时间戳超窗 / nonce 重放」这类失败在这里查不到，
表现为「完全没有数据」。故 ``total=0`` 时不能断言未接入，
只能列出候选原因让运维自行排查。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from fangyu_shared.clickhouse_manager import ClickHouseClient, get_clickhouse
from fangyu_shared.schemas.common import SuccessResponse

from src.application.services.site_service import SiteService
from src.infrastructure.clickhouse.access_log_query import AccessLogQueryService
from src.interfaces.http.dependencies import get_site_service, require_permission
from .schemas import (
    IngressStatSchema,
    IntegrationDiagnosticsSchema,
    IntegrationFindingSchema,
)

router = APIRouter(prefix="/sites", tags=["diagnostics"])

# 判定阈值。派生指纹与行为事件的占比阈值取相对宽松的值，
# 避免小流量站点因个别异常请求就被判成接入错误。
_DERIVED_RATIO_ALERT = 0.5
_UNKNOWN_RATIO_ALERT = 0.2


def _service(client: ClickHouseClient = Depends(get_clickhouse)) -> AccessLogQueryService:
    return AccessLogQueryService(client)


def _finding(
    level: str, code: str, title: str, detail: str, suggestion: str
) -> IntegrationFindingSchema:
    return IntegrationFindingSchema(
        level=level, code=code, title=title, detail=detail, suggestion=suggestion
    )


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _analyze(
    *,
    access_mode: str,
    is_active: bool,
    stats: list[IngressStatSchema],
    hours: int,
) -> tuple[str, list[IntegrationFindingSchema]]:
    """把聚合指标翻译成人能直接照着修的结论。

    返回 ``(status, findings)``，status 取值 ok / warning / error / no_data。
    """
    findings: list[IntegrationFindingSchema] = []
    total = sum(s.total for s in stats)

    if not is_active:
        findings.append(
            _finding(
                "error",
                "site_inactive",
                "站点已停用",
                "站点处于停用状态，网关已删除其 App Key 映射，所有决策请求都会被拒绝。",
                "在应用管理中重新启用该站点；注意停用与密钥填错的网关报错完全相同。",
            )
        )

    if total == 0:
        findings.append(
            _finding(
                "error",
                "no_traffic",
                f"近 {hours} 小时无任何决策记录",
                "该站点没有产生任何决策事件。可能是埋码未生效，也可能是请求在网关"
                "鉴权阶段就被拒绝——验签失败的请求不会落库，因此这里无法区分。",
                "依次核对：① 埋码/适配器是否已部署上线；② X-App-Key 是否为该站点的 site_id；"
                "③ App Secret 是否与站点一致；④ 服务器时钟是否与网关相差超过 5 分钟；"
                "⑤ 网关地址是否可达。可查看网关日志中的 request_signature_rejected 记录定位具体原因。",
            )
        )
        return "no_data", findings

    observed = {s.ingress: s for s in stats}

    # 配置与实测比对：这是本页最核心的一条诊断
    if access_mode not in observed:
        actual = "、".join(f"{s.ingress}（{s.total} 次）" for s in stats)
        findings.append(
            _finding(
                "error",
                "ingress_mismatch",
                "实测接入方式与站点配置不一致",
                f"站点配置的接入模式为 {access_mode}，但实际流量全部来自：{actual}。",
                f"若接入方式已调整，请把站点的接入模式改为实际使用的那种；"
                f"否则检查 {access_mode} 侧埋码为何没有生效。",
            )
        )
    elif len(stats) > 1:
        others = "、".join(f"{s.ingress}（{s.total} 次）" for s in stats if s.ingress != access_mode)
        findings.append(
            _finding(
                "warning",
                "mixed_ingress",
                "存在多种接入来源",
                f"除配置的 {access_mode} 之外，还观测到：{others}。混合接入本身允许，"
                "但两条路径的信号丰富度不同，聚合指标会被稀释。",
                "确认这是有意的多路接入；否则排查多余来源是哪个环境残留的埋码。",
            )
        )

    for stat in stats:
        if stat.ingress == "sdk":
            _analyze_sdk(stat, findings)
        elif stat.ingress == "adapter":
            _analyze_adapter(stat, findings)

        if stat.total and _ratio(stat.unknown_verdict_count, stat.total) > _UNKNOWN_RATIO_ALERT:
            findings.append(
                _finding(
                    "warning",
                    f"unknown_verdict_{stat.ingress}",
                    f"{stat.ingress} 存在较多未判定请求",
                    f"{stat.unknown_verdict_count} / {stat.total} 次请求的判定结果为 unknown，"
                    "通常意味着入参缺失导致网关无法完成评估。",
                    "检查上报字段是否完整：adapter 必须带 ip，sdk 必须带 fingerprint。",
                )
            )

    if not findings:
        findings.append(
            _finding(
                "ok",
                "healthy",
                "接入正常",
                f"近 {hours} 小时共 {total} 次决策请求，接入方式与配置一致，未发现异常信号。",
                "无需处理。",
            )
        )

    if any(f.level == "error" for f in findings):
        return "error", findings
    if any(f.level == "warning" for f in findings):
        return "warning", findings
    return "ok", findings


def _analyze_sdk(stat: IngressStatSchema, findings: list[IntegrationFindingSchema]) -> None:
    """SDK 侧特有信号：真指纹与行为时序都在就算接好了。"""
    derived_ratio = _ratio(stat.derived_count, stat.total)
    if derived_ratio > _DERIVED_RATIO_ALERT:
        findings.append(
            _finding(
                "error",
                "sdk_derived_fingerprint",
                "SDK 指纹由网关派生，埋码等于未生效",
                f"{stat.derived_count} / {stat.total} 次 SDK 请求的指纹是网关按 IP+UA 派生的，"
                "说明前端没有采集到 Evercookie 指纹。此时 SDK 的核心能力并未起作用。",
                "确认 SdSdk.protect() 已真正执行（检查控制台报错）、脚本未被 CSP 或广告拦截器阻断、"
                "且未给 script 标签加 defer 导致内联调用先于 SDK 加载执行。",
            )
        )
    if stat.behavior_count == 0:
        findings.append(
            _finding(
                "warning",
                "sdk_no_behavior",
                "SDK 未上报任何行为事件",
                "所有 SDK 请求都没有带行为时序数据。行为信号是 SDK 相对适配器的主要优势，"
                "缺失时评分维度会退化。",
                "确认页面停留时间足够触发行为采集，且未在 onload 前就跳走；"
                "若刻意关闭了行为采集可忽略此项。",
            )
        )


@router.get(
    "/{site_id}/integration-diagnostics",
    response_model=SuccessResponse[IntegrationDiagnosticsSchema],
    dependencies=[Depends(require_permission("app.read"))],
    summary="SDK / Adapter 接入诊断",
)
async def integration_diagnostics(
    site_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    site_service: SiteService = Depends(get_site_service),
    log_service: AccessLogQueryService = Depends(_service),
) -> SuccessResponse[IntegrationDiagnosticsSchema]:
    """诊断某站点的接入健康度：实测接入方式、最后活跃时间与异常信号。

    站点不存在时由 SiteService 抛出 ResourceNotFoundException（404）。
    """
    site = await site_service.get(site_id)

    end = datetime.utcnow()
    start = end - timedelta(hours=hours)
    rows = await log_service.ingress_diagnostics(site_id=site_id, start=start, end=end)

    stats = [
        IngressStatSchema(
            ingress=str(row.get("ingress") or "unknown"),
            host=str(row.get("host") or ""),
            total=int(row.get("total") or 0),
            derived_count=int(row.get("derived_count") or 0),
            behavior_count=int(row.get("behavior_count") or 0),
            restore_count=int(row.get("restore_count") or 0),
            unknown_verdict_count=int(row.get("unknown_verdict_count") or 0),
            hostile_count=int(row.get("hostile_count") or 0),
            suspicious_count=int(row.get("suspicious_count") or 0),
            clean_count=int(row.get("clean_count") or 0),
            clock_banned_count=int(row.get("clock_banned_count") or 0),
            unique_fingerprints=int(row.get("unique_fingerprints") or 0),
            unique_ips=int(row.get("unique_ips") or 0),
            avg_cost_ms=round(float(row.get("avg_cost_ms") or 0), 2),
            first_seen_at=row.get("first_seen_at"),
            last_seen_at=row.get("last_seen_at"),
        )
        for row in rows
    ]

    status, findings = _analyze(
        access_mode=site.access_mode,
        is_active=site.is_active,
        stats=stats,
        hours=hours,
    )
    last_seen = max((s.last_seen_at for s in stats if s.last_seen_at), default=None)

    return SuccessResponse(
        data=IntegrationDiagnosticsSchema(
            site_id=site_id,
            site_name=site.name,
            domain=site.domain,
            is_active=site.is_active,
            configured_access_mode=site.access_mode,
            configured_sdk_version=site.sdk_version,
            gateway_url=site.gateway_url,
            window_hours=hours,
            total_requests=sum(s.total for s in stats),
            last_seen_at=last_seen,
            status=status,
            ingress_stats=stats,
            findings=findings,
        )
    )


def _analyze_adapter(stat: IngressStatSchema, findings: list[IntegrationFindingSchema]) -> None:
    """Adapter 侧：派生指纹是设计预期，不构成问题。"""
    if stat.unique_ips <= 1 and stat.total > 20:
        findings.append(
            _finding(
                "warning",
                "adapter_single_ip",
                "适配器上报的客户端 IP 疑似未透传",
                f"{stat.total} 次请求仅来自 {stat.unique_ips} 个 IP，很可能上报的是反向代理自身"
                "的地址而非真实访客 IP。这会让所有基于 IP 的判定失效。",
                "检查适配器取 IP 的逻辑是否正确读取 X-Forwarded-For / X-Real-IP，"
                "并确认上游代理确实写入了这些头。",
            )
        )

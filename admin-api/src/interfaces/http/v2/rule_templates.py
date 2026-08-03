"""规则模板目录与规则试跑接口。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from fangyu_shared.rules.operators import apply_operator, evaluate_conditions, read_path
from fangyu_shared.schemas.common import BaseSchema, SuccessResponse
from fangyu_shared.schemas.disposition import (
    ChallengeKind,
    Disposition,
    Mechanism,
    Verdict,
    allow,
    challenge,
    deny,
    not_found,
    observe,
    redirect,
    serve_alt,
)
from fangyu_shared.schemas.rule import DecisionRule, RuleKind
from fangyu_shared.ua import parse_user_agent

from src.interfaces.http.dependencies import require_permission

router = APIRouter(prefix="/rules", tags=["rules"])


class RuleTemplateSchema(BaseSchema):
    """规则模板。

    ``kind`` 决定模板产出决策规则还是打分规则：决策模板带 ``disposition``，
    打分模板带 ``weight``，两者互斥。
    """

    id: str
    name: str
    description: str
    priority: str
    kind: RuleKind = RuleKind.DECISION
    conditions: list[dict[str, Any]]
    disposition: Disposition | None = None
    weight: int | None = None


class RulePreviewRequest(BaseSchema):
    rule: DecisionRule
    context: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = Field(default=None, description="用于实时 IP 解析的原始 IP 地址（admin 试跑时直接传入）")
    user_agent: str | None = Field(default=None, alias="userAgent", description="用于实时 UA 解析的原始字符串")


class ConditionTrace(BaseSchema):
    field: str
    op: str
    expected: Any
    actual: Any
    matched: bool


class RulePreviewResponse(BaseSchema):
    matched: bool
    rule_id: int | None = Field(default=None, alias="ruleId")
    verdict: Verdict | None = None
    mechanism: Mechanism | None = None
    target_url: str | None = Field(default=None, alias="targetUrl")
    http_status: int | None = Field(default=None, alias="httpStatus")
    duration_ms: float = Field(alias="durationMs")
    conditions: list[ConditionTrace] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict, description="试跑时实际使用的完整上下文，含 ua.* 解析结果")


_TEMPLATES = [
    RuleTemplateSchema(
        id="block-country",
        name="国家/地区阻断",
        description="命中指定国家或地区后执行阻断。国家码为 ISO 3166-1 alpha-2。",
        priority="high",
        disposition=deny(),
        conditions=[{"field": "ip.country", "op": "in_ci", "value": ["RU", "KP"]}],
    ),
    RuleTemplateSchema(
        id="allow-country-only",
        name="仅放行指定国家",
        description=(
            "业务只面向特定市场时，非目标国家一律阻断。"
            "第一条件排除地理数据缺失的情况：MMDB 未加载或内网地址时 ip.country 为空，"
            "否定类操作符会命中，若不排除则退化为全站阻断。"
        ),
        priority="critical",
        disposition=deny(),
        conditions=[
            {"field": "ip.country", "op": "neq", "value": None},
            {"field": "ip.country", "op": "not_in_ci", "value": ["CN", "HK", "MO", "TW"]},
        ],
    ),
    RuleTemplateSchema(
        id="challenge-new-device",
        name="新设备挑战",
        description=(
            "对首次出现的设备执行验证码挑战。"
            "以累计请求数为判据，与 scorer 的新设备识别口径一致。"
        ),
        priority="normal",
        disposition=challenge(ChallengeKind.CAPTCHA),
        conditions=[{"field": "device.totalRequests", "op": "eq", "value": 0}],
    ),
    RuleTemplateSchema(
        id="path-block",
        name="敏感路径阻断",
        description=(
            "命中敏感路径前缀后执行阻断。用 regex 而非 in："
            "in 是精确相等，只能挡住 /admin 本身，挡不住 /admin/users。"
        ),
        priority="critical",
        disposition=deny(),
        conditions=[{"field": "request.path", "op": "regex", "value": "^/(admin|checkout)(/|$)"}],
    ),
    RuleTemplateSchema(
        id="block-datacenter",
        name="数据中心 IP 阻断",
        description="来源为云厂商/IDC 机房的流量通常不是真实终端用户，直接阻断。",
        priority="high",
        disposition=deny(),
        conditions=[{"field": "ip.isDatacenter", "op": "eq", "value": True}],
    ),
    RuleTemplateSchema(
        id="challenge-proxy-vpn",
        name="代理/VPN 挑战",
        description="识别为代理或 VPN 出口的请求执行 JS 挑战，兼顾隐私用户体验。",
        priority="high",
        disposition=challenge(ChallengeKind.JS),
        conditions=[{"field": "ip.isProxy", "op": "eq", "value": True}],
    ),
    RuleTemplateSchema(
        id="allow-mobile-network",
        name="移动网络放行",
        description="蜂窝网络出口 IP 共享度高、误杀代价大，命中后仅记录不拦截。",
        priority="low",
        disposition=observe(),
        conditions=[{"field": "ip.isMobileNetwork", "op": "eq", "value": True}],
    ),
    RuleTemplateSchema(
        id="block-asn",
        name="ASN 精准阻断",
        description="按自治域号阻断特定网络运营商，支持 4134 / \"AS4134\" 两种写法。",
        priority="high",
        disposition=deny(),
        conditions=[{"field": "ip.asn", "op": "asn_in", "value": [14061, 16509, 45102]}],
    ),
    RuleTemplateSchema(
        id="ip-whitelist",
        name="IP 段白名单",
        description="办公网/合作方网段直接放行，建议配最高权重优先短路。",
        priority="critical",
        disposition=allow(),
        conditions=[{"field": "ip.ip", "op": "cidr_list_in", "value": ["10.0.0.0/8", "203.0.113.0/24"]}],
    ),
    RuleTemplateSchema(
        id="ip-blacklist",
        name="IP 段黑名单",
        description="已确认恶意的网段静默丢弃，不回显拦截原因避免对抗。",
        priority="critical",
        disposition=not_found(),
        conditions=[{"field": "ip.ip", "op": "cidr_list_in", "value": ["198.51.100.0/24"]}],
    ),
    RuleTemplateSchema(
        id="allow-search-engine",
        name="搜索引擎放行",
        description="放行 Googlebot/Bingbot/Baiduspider 等搜索引擎，避免影响 SEO 收录。",
        priority="critical",
        disposition=observe(),
        conditions=[{"field": "ua.crawler_category", "op": "eq", "value": "search_engine"}],
    ),
    RuleTemplateSchema(
        id="block-ai-crawler",
        name="AI 语料爬虫阻断",
        description="阻断 GPTBot/ClaudeBot/CCBot/Bytespider 等 AI 训练数据抓取。",
        priority="high",
        disposition=deny(),
        conditions=[{"field": "ua.crawler_category", "op": "eq", "value": "ai_crawler"}],
    ),
    RuleTemplateSchema(
        id="block-security-scanner",
        name="安全扫描器阻断",
        description="sqlmap/nikto/nuclei 等攻击扫描工具静默丢弃。",
        priority="critical",
        disposition=not_found(),
        conditions=[{"field": "ua.crawler_category", "op": "eq", "value": "security"}],
    ),
    RuleTemplateSchema(
        id="challenge-seo-crawler",
        name="SEO 工具限流",
        description="Ahrefs/Semrush/MJ12 等商业 SEO 爬虫消耗带宽但无业务价值。",
        priority="normal",
        disposition=challenge(ChallengeKind.JS),
        conditions=[{"field": "ua.crawler_vendor", "op": "in_ci", "value": ["ahrefs", "semrush", "majestic", "moz"]}],
    ),
    RuleTemplateSchema(
        id="block-http-library",
        name="脚本客户端阻断",
        description="curl/python-requests/Go-http-client 等非浏览器客户端直连业务接口。",
        priority="high",
        disposition=deny(),
        conditions=[{"field": "ua.crawler_category", "op": "eq", "value": "library"}],
    ),
    RuleTemplateSchema(
        id="block-headless-browser",
        name="无头浏览器阻断",
        description="HeadlessChrome/Puppeteer/Playwright/Selenium 自动化环境。",
        priority="high",
        disposition=deny(),
        conditions=[
            {
                "field": "ua.crawler_vendor",
                "op": "in_ci",
                "value": ["headless-chrome", "puppeteer", "playwright", "selenium", "phantomjs"],
            }
        ],
    ),
    RuleTemplateSchema(
        id="block-empty-ua",
        name="空 UA 阻断",
        description="正常浏览器不会发送空 User-Agent。",
        priority="high",
        disposition=deny(),
        conditions=[{"field": "ua.is_empty", "op": "eq", "value": True}],
    ),
    RuleTemplateSchema(
        id="challenge-desktop-only-path",
        name="移动端访问桌面端接口挑战",
        description="设备类型与业务预期不符时挑战，用于识别 UA 伪造。",
        priority="normal",
        disposition=challenge(ChallengeKind.JS),
        conditions=[
            {"field": "request.path", "op": "startswith", "value": "/desktop/"},
            {"field": "ua.device_type", "op": "in", "value": ["mobile", "tablet"]},
        ],
    ),
    RuleTemplateSchema(
        id="block-legacy-os",
        name="老旧操作系统阻断",
        description="Windows XP/Vista 等停止维护的系统多为伪造 UA 或失陷主机。",
        priority="normal",
        disposition=challenge(ChallengeKind.CAPTCHA),
        conditions=[
            {"field": "ua.os", "op": "eq", "value": "windows"},
            {"field": "ua.os_version", "op": "in_ci", "value": ["XP", "Vista"]},
        ],
    ),
    RuleTemplateSchema(
        id="block-ie",
        name="IE 浏览器挑战",
        description="IE 已停止支持，真实占比极低，常被自动化工具冒用。",
        priority="low",
        disposition=challenge(ChallengeKind.JS),
        conditions=[{"field": "ua.browser", "op": "eq", "value": "ie"}],
    ),
    RuleTemplateSchema(
        id="brand-specific-rule",
        name="设备品牌定向策略",
        description="按设备品牌定向下发策略，用于渠道作弊或特定机型风控。",
        priority="normal",
        disposition=observe(),
        conditions=[{"field": "ua.brand", "op": "in_ci", "value": ["xiaomi", "oppo", "vivo"]}],
    ),
    RuleTemplateSchema(
        id="datacenter-non-browser",
        name="机房来源且非浏览器",
        description="数据中心 IP + 非浏览器客户端双条件命中，几乎必然是自动化流量。",
        priority="critical",
        disposition=not_found(),
        conditions=[
            {"field": "ip.isDatacenter", "op": "eq", "value": True},
            {"field": "ua.client_type", "op": "neq", "value": "browser"},
        ],
    ),
    RuleTemplateSchema(
        id="serve-alt-to-crawler",
        name="爬虫投放替代页",
        description=(
            "对爬虫投放替代内容而非直接拦截。相比 403，替代页不暴露识别结果，"
            "降低对抗升级动机。"
        ),
        priority="high",
        disposition=serve_alt("/alt/index.html"),
        conditions=[{"field": "ua.is_bot", "op": "eq", "value": True}],
    ),
    RuleTemplateSchema(
        id="redirect-suspect-region",
        name="可疑地区跳转分流",
        description=(
            "命中后 302 跳转到指定地址，支持 {host}/{path}/{query} 占位符，"
            "由网关按当次请求渲染。"
        ),
        priority="normal",
        disposition=redirect("https://{host}/verify?from={path}"),
        conditions=[{"field": "ip.country", "op": "in_ci", "value": ["RU", "IR"]}],
    ),
    RuleTemplateSchema(
        id="score-proxy-signal",
        name="代理信号加分（打分规则）",
        description=(
            "打分规则不终止流水线，只贡献权重，最终由评分阈值决定处置。"
            "适合弱信号叠加判断。"
        ),
        priority="normal",
        kind=RuleKind.SCORING,
        weight=35,
        conditions=[{"field": "ip.isProxy", "op": "eq", "value": True}],
    ),
]


@router.get(
    "/templates",
    response_model=SuccessResponse[list[RuleTemplateSchema]],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def list_rule_templates() -> SuccessResponse[list[RuleTemplateSchema]]:
    return SuccessResponse(data=_TEMPLATES)


@router.post(
    "/preview",
    response_model=SuccessResponse[RulePreviewResponse],
    dependencies=[Depends(require_permission("rule.read"))],
)
async def preview_rule(payload: RulePreviewRequest) -> SuccessResponse[RulePreviewResponse]:
    started = time.perf_counter()

    ctx = dict(payload.context)

    if payload.user_agent is not None:
        ua_result = parse_user_agent(payload.user_agent)
        ctx.setdefault("ua", {})
        ctx["ua"] = {**ua_result.to_dict(), **ctx["ua"]}

    if payload.ip is not None:
        ctx.setdefault("ip", {})
        ctx["ip"].setdefault("ip", payload.ip)
        ctx["request"] = ctx.get("request", {})
        ctx["request"].setdefault("user_agent", payload.user_agent or "")

    # 逐条 trace 供前端展示，仅用于可视化；命中结论一律由 evaluator 给出，
    # 不在此处重复实现 AND/OR，避免与 gateway 漂移。
    traces = [
        ConditionTrace(
            field=condition.field,
            op=condition.op,
            expected=condition.value,
            actual=read_path(ctx, condition.field),
            matched=apply_operator(
                condition.op, read_path(ctx, condition.field), condition.value
            ),
        )
        for condition in payload.rule.conditions
    ]

    matched = evaluate_conditions(
        payload.rule.conditions, ctx, match_all=payload.rule.match_all
    )

    # 优先用 effective_match_disposition，兼容新版双路规则与旧版单路规则
    disposition = payload.rule.effective_match_disposition if matched else None
    return SuccessResponse(
        data=RulePreviewResponse(
            matched=matched,
            ruleId=payload.rule.id if matched else None,
            verdict=disposition.verdict if matched else None,
            mechanism=disposition.mechanism if matched else None,
            targetUrl=disposition.target.url if matched else None,
            httpStatus=disposition.effective_status if matched else None,
            durationMs=round((time.perf_counter() - started) * 1000, 3),
            conditions=traces,
            context=ctx,
        )
    )

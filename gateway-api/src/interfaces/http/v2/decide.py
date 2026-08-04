"""决策 HTTP 接口。

安全模型：
- 所有 ``/decide`` / ``/decide/fast`` 请求必须携带有效 API Key。
- Gateway 内部经由 :func:`require_app_key` 依赖把 API Key 解析成 ``app_id``。
- 请求体中的 ``appId`` 若与解析结果不一致，直接返回 401，避免客户端伪造调用其他租户。

IP 的来源
---------
``ingress=sdk`` 时 ``context.ip`` **一律由服务端从 socket peer 覆写**，客户端
传什么都不作数。浏览器本来就不知道自己的出口 IP，若采信客户端上报，任何持有
API Key 的人都能把自己的 IP 报成干净地址绕过信誉与频控。

读 ``X-Real-IP`` 而非 ``X-Forwarded-For``：前者由反向代理用 ``$remote_addr``
单值覆写，客户端伪造的同名头会被直接替换；后者是追加语义
（``$proxy_add_x_forwarded_for``），客户端可在链首注入任意地址。

前提：gateway 只能通过受信反向代理暴露，不得直接对公网监听。否则攻击者可
自带 ``X-Real-IP`` 伪造来源。容器部署下 socket peer 恒为网桥 IP
（如 ``172.28.0.1``），无法用作访客标识，故必须依赖代理头。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from fangyu_shared.exceptions import AuthenticationException, ValidationException
from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.decision import DecisionRequest, DecisionResponse, IngressKind

from src.application.services.decision_service import DecisionService
from src.interfaces.http.dependencies import get_decision_service
from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key

router = APIRouter(tags=["decide"])


def _resolve_context_ip(payload: DecisionRequest, request: Request) -> DecisionRequest:
    """填充 / 覆写 ``context.ip``。

    - ``ingress=sdk``：优先读 ``X-Real-IP`` 头（反向代理已设为真实客户端地址），
      回退 socket peer。直接用 socket peer 在容器网络环境中会拿到网桥 IP。
    - ``ingress=adapter``：保留站点服务端上报的访客 IP（schema 已强制必填）；
      此时 socket peer 是站点服务器，不是访客。
    """
    ctx = payload.context
    if ctx.ingress == IngressKind.ADAPTER:
        return payload

    # 优先从 X-Real-IP 头读取（nginx 已设为 $remote_addr）
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return payload.model_copy(update={"context": ctx.model_copy(update={"ip": real_ip.strip()})})

    # 回退 socket peer
    client = request.client
    peer = client.host if client and client.host else None
    if not peer:
        # 没有 socket peer（ASGI 测试客户端或异常传输层）且客户端也没给值：
        # 缺 IP 会让下游频控/缓存键退化，宁可显式拒绝也不要静默降级。
        if ctx.ip is None:
            raise ValidationException("无法确定客户端 IP")
        return payload

    return payload.model_copy(update={"context": ctx.model_copy(update={"ip": peer})})


def _resolve_client_language(payload: DecisionRequest, request: Request) -> DecisionRequest:
    """客户端未上报语言时，从 Accept-Language 请求头回填。

    适配器可能不采集该字段，内联脚本也可能遗漏。HTTP 头是最稳兜底：
    浏览器默认发送、与 navigator.language 口径一致。
    """
    ctx = payload.context
    if ctx.client_language:
        return payload

    accept_lang = request.headers.get("accept-language")
    if not accept_lang:
        return payload

    # Accept-Language: zh-CN,zh;q=0.9,en;q=0.8 → 取权重最高的第一段
    primary = accept_lang.split(",")[0].strip().split(";")[0].strip()
    if not primary:
        return payload

    return payload.model_copy(update={"context": ctx.model_copy(update={"client_language": primary})})


def _guard_app_id(payload: DecisionRequest, resolved: ResolvedAppKey) -> DecisionRequest:
    """比对 payload.appId 与 API Key 解析出的 app_id，冲突即拒绝。

    适配器无需在 context 中填写 appId；gateway 统一以 X-App-Key 派生的
    app_id 为准，并回填到 context 中，以便下游使用。
    """
    if resolved.app_id <= 0:
        # 免鉴权模式（仅本地/debug）：payload 必须自带 appId。
        if payload.context.app_id <= 0:
            raise AuthenticationException("缺少 API Key")
        return payload

    if payload.context.app_id > 0 and payload.context.app_id != resolved.app_id:
        raise AuthenticationException("API Key 与 appId 不匹配")

    # 统一以 API Key 派生的 app_id 回填，适配器可省略 appId 字段。
    return payload.model_copy(
        update={"context": payload.context.model_copy(update={"app_id": resolved.app_id})}
    )


@router.post(
    "/decide",
    response_model=SuccessResponse[DecisionResponse],
    summary="标准决策接口（含详细阶段信息可选）",
)
async def decide(
    payload: DecisionRequest,
    request: Request,
    resolved: ResolvedAppKey = Depends(require_app_key),
    service: DecisionService = Depends(get_decision_service),
) -> SuccessResponse[DecisionResponse]:
    guarded = _resolve_client_language(
        _resolve_context_ip(_guard_app_id(payload, resolved), request), request
    )
    response = await service.decide(guarded)
    return SuccessResponse[DecisionResponse](data=response, request_id=response.request_id)


@router.post(
    "/decide/fast",
    response_model=DecisionResponse,
    summary="低延迟通道，只返回核心字段",
)
async def decide_fast(
    payload: DecisionRequest,
    request: Request,
    resolved: ResolvedAppKey = Depends(require_app_key),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    guarded = _resolve_client_language(
        _resolve_context_ip(_guard_app_id(payload, resolved), request), request
    )
    fast_payload = guarded.model_copy(update={"require_details": False})
    return await service.decide(fast_payload)

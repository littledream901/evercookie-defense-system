"""决策 HTTP 接口。

安全模型：
- 所有 ``/decide`` / ``/decide/fast`` 请求必须携带有效 API Key。
- Gateway 内部经由 :func:`require_app_key` 依赖把 API Key 解析成 ``app_id``。
- 请求体中的 ``appId`` 若与解析结果不一致，直接返回 401，避免客户端伪造调用其他租户。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from fangyu_shared.exceptions import AuthenticationException
from fangyu_shared.schemas.common import SuccessResponse
from fangyu_shared.schemas.decision import DecisionRequest, DecisionResponse

from src.application.services.decision_service import DecisionService
from src.interfaces.http.dependencies import get_decision_service
from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key

router = APIRouter(tags=["decide"])


def _guard_app_id(payload: DecisionRequest, resolved: ResolvedAppKey) -> DecisionRequest:
    """比对 payload.appId 与 API Key 解析出的 app_id，冲突即拒绝。"""
    if resolved.app_id <= 0:
        # 免鉴权模式（仅本地/debug）：payload 必须自带 appId。
        if payload.context.app_id <= 0:
            raise AuthenticationException("缺少 API Key")
        return payload

    if payload.context.app_id and payload.context.app_id != resolved.app_id:
        raise AuthenticationException("API Key 与 appId 不匹配")

    # payload 未显式给 appId，或 appId 与 key 一致；统一以 key 派生的 app_id 为准。
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
    resolved: ResolvedAppKey = Depends(require_app_key),
    service: DecisionService = Depends(get_decision_service),
) -> SuccessResponse[DecisionResponse]:
    guarded = _guard_app_id(payload, resolved)
    response = await service.decide(guarded)
    return SuccessResponse[DecisionResponse](data=response, request_id=response.request_id)


@router.post(
    "/decide/fast",
    response_model=DecisionResponse,
    summary="低延迟通道，只返回核心字段",
)
async def decide_fast(
    payload: DecisionRequest,
    resolved: ResolvedAppKey = Depends(require_app_key),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    guarded = _guard_app_id(payload, resolved)
    fast_payload = guarded.model_copy(update={"require_details": False})
    return await service.decide(fast_payload)

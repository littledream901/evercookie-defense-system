"""SDK 生命周期接口：init / status / heartbeat。

这三个端点服务于浏览器 SDK 的运行时需求，与决策链路解耦：

``/sdk/init``
    下发站点配置与**服务端时间**。后者用于校正客户端时钟——行为事件的时序
    依赖 ``clientTsMs``，而网关会把偏移超过 ±5 分钟的时间戳整条替换为服务端
    时间（见 ``normalize_event_time``），那样会丢掉事件间的相对顺序。SDK 拿到
    skew 后自行校正，时钟不准的设备也能保住时序。
``/sdk/status``
    轻量版本探测，供 SDK 轮询判断配置是否变更，避免每次都拉全量 init。
``/sdk/heartbeat``
    行为事件的回传通道。**这是 V2 补的关键缺口**：``decide`` 之后才产生的
    行为事件在旧设计里没有任何入库路径，采集了但永远送不到时序库。

鉴权
----
与 ``/v2/decide`` 同级保护：这三个端点都会按 ``appId`` 读写站点数据，
不鉴权等于让任意调用方往他人的时序库里灌数据。故在
``AppKeyEnforcementMiddleware`` 的 ``protected_patterns`` 中一并覆盖。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request

from fangyu_shared.clock.windows import MAX_BEHAVIOR_EVENTS_PER_REQUEST
from fangyu_shared.exceptions import AuthenticationException
from fangyu_shared.logging import get_logger
from fangyu_shared.schemas.clock import BehaviorEvent
from fangyu_shared.schemas.common import BaseSchema, SuccessResponse
from pydantic import Field

from src.config import GatewaySettings
from src.infrastructure.clock.repository import ClockRepository
from src.interfaces.http.dependencies import (
    get_clock_repository,
    get_gateway_settings,
)
from src.interfaces.http.middleware.app_key import ResolvedAppKey, require_app_key

_logger = get_logger("gateway.sdk")

router = APIRouter(prefix="/sdk", tags=["sdk"])

SDK_VERSION = "2.0.0"
"""服务端认可的 SDK 版本。客户端版本低于此值时仍然服务，只在日志里留痕。"""


# ── 请求 / 响应契约 ──


class SdkBehaviorPolicy(BaseSchema):
    """下发给 SDK 的行为采集策略。"""

    enabled: bool = True
    interval_ms: int = Field(default=200, alias="intervalMs", ge=0)
    """同类高频事件的最小采样间隔。"""
    max_events: int = Field(
        default=MAX_BEHAVIOR_EVENTS_PER_REQUEST, alias="maxEvents", ge=1
    )
    """单次请求携带的事件上限，与网关的 ``MAX_BEHAVIOR_EVENTS_PER_REQUEST`` 对齐。"""


class SdkInitRequest(BaseSchema):
    site_id: int = Field(default=0, alias="siteId", ge=0)
    """站点主键（Site.id）。注意：
    sdk_version: str = Field(default="", alias="sdkVersion", max_length=32)


class SdkInitResponse(BaseSchema):
    site_id: int = Field(..., alias="siteId")
    """站点主键（Site.id）"""
    sdk_version: str = Field(default=SDK_VERSION, alias="sdkVersion")
    server_time_ms: int = Field(..., alias="serverTimeMs")
    config_version: str = Field(default="", alias="configVersion")
    collect_behavior: bool = Field(default=True, alias="collectBehavior")
    behavior: SdkBehaviorPolicy = Field(default_factory=SdkBehaviorPolicy)


class SdkStatusResponse(BaseSchema):
    site_id: int = Field(..., alias="siteId")
    """站点主键（Site.id）"""
    config_version: str = Field(default="", alias="configVersion")
    server_time_ms: int = Field(..., alias="serverTimeMs")


class SdkHeartbeatRequest(BaseSchema):
    site_id: int = Field(default=0, alias="siteId", ge=0)
    """站点主键（Site.id）"""
    fingerprint: str = Field(default="", max_length=128)
    sdk_version: str = Field(default="", alias="sdkVersion", max_length=32)
    behavior_events: list[BehaviorEvent] = Field(
        default_factory=list,
        alias="behaviorEvents",
        max_length=MAX_BEHAVIOR_EVENTS_PER_REQUEST,
    )


class SdkHeartbeatResponse(BaseSchema):
    accepted: int = 0
    """实际入库的事件条数。0 可能是没有事件，也可能是 Clock 未启用。"""
    server_time_ms: int = Field(..., alias="serverTimeMs")
    config_version: str = Field(default="", alias="configVersion")


# ── 内部 ──


def _now_ms() -> int:
    return int(time.time() * 1000)


def _resolve_app_id(claimed: int, resolved: ResolvedAppKey) -> int:
    """确定 app_id，口径与 ``/v2/decide`` 的 ``_guard_app_id`` 一致。

    以 API Key 派生的 site_id 为准；请求体自报的值若与之冲突直接拒绝，
    避免持有 A 站点 Key 的调用方往 B 站点写数据。
    
    Note:
        返回值实际是站点主键（Site.id），函数名保持历史兼容。
    """
    if resolved.site_id <= 0:
        # 免鉴权模式（仅本地 / debug）：必须自报 appId
        if claimed <= 0:
            raise AuthenticationException("缺少 API Key")
        return claimed

    if claimed and claimed != resolved.site_id:
        raise AuthenticationException("API Key 与 appId 不匹配")
    return resolved.site_id


def _config_version(settings: GatewaySettings, app_id: int) -> str:
    """配置版本标识。

    当前用「SDK 版本 + 站点开关」组合派生，站点改开关时 SDK 能感知到变化。
    规则配置的版本号目前不参与——规则变更由网关侧的决策缓存 TTL 自然收敛，
    不需要客户端配合。
    """
    flags = f"{int(settings.clock_enabled)}{int(settings.whitelist_enabled)}"
    return f"{SDK_VERSION}-{app_id}-{flags}"


def _behavior_policy(settings: GatewaySettings) -> SdkBehaviorPolicy:
    return SdkBehaviorPolicy(
        enabled=settings.clock_enabled,
        intervalMs=200,
        maxEvents=MAX_BEHAVIOR_EVENTS_PER_REQUEST,
    )


# ── 路由 ──


@router.post(
    "/init",
    response_model=SuccessResponse[SdkInitResponse],
    summary="SDK 初始化：下发站点配置与服务端时间",
)
async def sdk_init(
    payload: SdkInitRequest,
    resolved: ResolvedAppKey = Depends(require_app_key),
    settings: GatewaySettings = Depends(get_gateway_settings),
) -> SuccessResponse[SdkInitResponse]:
    site_id = _resolve_site_id(payload.site_id, resolved)

    if payload.sdk_version and payload.sdk_version != SDK_VERSION:
        # 不拒绝旧版本：站点的 SDK 更新节奏不由网关控制，硬拒会直接打断线上流量
        _logger.info(
            "sdk_version_mismatch",
            app_id=app_id,
            client_version=payload.sdk_version,
            server_version=SDK_VERSION,
        )

    data = SdkInitResponse(
        siteId=site_id,
        sdkVersion=SDK_VERSION,
        serverTimeMs=_now_ms(),
        configVersion=_config_version(settings, site_id),
        collectBehavior=settings.clock_enabled,
        behavior=_behavior_policy(settings),
    )
    return SuccessResponse[SdkInitResponse](data=data)


@router.get(
    "/status",
    response_model=SuccessResponse[SdkStatusResponse],
    summary="配置版本探测：供 SDK 轮询判断是否需要重新 init",
)
async def sdk_status(
    app_id: int = Query(default=0, alias="appId", ge=0),
    resolved: ResolvedAppKey = Depends(require_app_key),
    settings: GatewaySettings = Depends(get_gateway_settings),
) -> SuccessResponse[SdkStatusResponse]:
    resolved_id = _resolve_app_id(app_id, resolved)
    data = SdkStatusResponse(
        siteId=resolved_id,
        configVersion=_config_version(settings, resolved_id),
        serverTimeMs=_now_ms(),
    )
    return SuccessResponse[SdkStatusResponse](data=data)


@router.post(
    "/heartbeat",
    response_model=SuccessResponse[SdkHeartbeatResponse],
    summary="心跳与行为事件回传",
)
async def sdk_heartbeat(
    payload: SdkHeartbeatRequest,
    request: Request,
    resolved: ResolvedAppKey = Depends(require_app_key),
    settings: GatewaySettings = Depends(get_gateway_settings),
    clock: ClockRepository | None = Depends(get_clock_repository),
) -> SuccessResponse[SdkHeartbeatResponse]:
    app_id = _resolve_app_id(payload.site_id, resolved)
    now_ms = _now_ms()

    accepted = 0
    if payload.behavior_events and clock is not None:
        # 指纹是时序库的分区键。缺指纹的事件无法归属到访客，落库只会产生
        # 一条永远长不大的孤儿序列，不如直接丢弃并留日志。
        if not payload.fingerprint:
            _logger.warning("behavior_dropped_no_fingerprint", app_id=app_id)
        else:
            try:
                accepted = await clock.store_behavior(
                    site_id,
                    payload.fingerprint,
                    payload.behavior_events,
                    now_ms=now_ms,
                )
            except Exception as exc:  # pragma: no cover - Redis 异常兜底
                # 行为入库失败不影响心跳本身：SDK 依赖心跳响应校正时钟与
                # 探测配置版本，为了一批可丢的事件而让心跳整体失败不划算。
                _logger.error("behavior_store_failed", site_id=site_id, error=str(exc))

    data = SdkHeartbeatResponse(
        accepted=accepted,
        serverTimeMs=now_ms,
        configVersion=_config_version(settings, app_id),
    )
    return SuccessResponse[SdkHeartbeatResponse](data=data)


__all__ = ["router", "SDK_VERSION"]

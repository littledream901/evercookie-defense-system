"""从上下文构建设备/IP 画像快照。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fangyu_shared.schemas.decision import DecisionContext
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile

from src.infrastructure.ua.parser import UAParser, UAResult


@dataclass(slots=True)
class ProfileSnapshot:
    """一次决策所需的画像视图。"""

    device: DeviceProfile
    ip: IpProfile
    ua: UAResult | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_evaluation_context(self) -> dict[str, Any]:
        """展开为规则条件可引用的扁平命名空间。

        规则 field 支持的顶层命名空间：
          device.*   设备画像（历史统计、信誉分）
          ip.*       IP 画像（地理、ASN、网络类型）
          ua.*       UA 解析结果（设备类型、OS、客户端、爬虫分类）
          request.*  本次请求实时属性
        """
        return {
            "device": self.device.model_dump(by_alias=True),
            "ip": self.ip.model_dump(by_alias=True),
            "ua": self.ua.to_dict() if self.ua else {},
            **self.context,
        }


class ProfileBuilder:
    """整合缓存与实时上下文构建 ProfileSnapshot。"""

    def __init__(self, ua_parser: UAParser | None = None) -> None:
        self._ua_parser = ua_parser or UAParser()

    def build(
        self,
        context: DecisionContext,
        *,
        cached_device: DeviceProfile | None = None,
        cached_ip: IpProfile | None = None,
        ip_lookup: dict[str, Any] | None = None,
    ) -> ProfileSnapshot:
        device = cached_device or DeviceProfile(
            fingerprint=context.fingerprint,
            deviceId=context.device_id,
        )
        ip = cached_ip or IpProfile(ip=str(context.ip))
        if ip_lookup:
            update_data = {k: v for k, v in ip_lookup.items() if v is not None}
            if update_data:
                ip = ip.model_copy(update=update_data)

        ua = self._ua_parser.parse(context.user_agent)

        return ProfileSnapshot(
            device=device,
            ip=ip,
            ua=ua,
            context={
                "request": {
                    "path": context.path,
                    "method": context.method,
                    "user_agent": context.user_agent,
                    "referer": context.referer,
                    "session_id": context.session_id,
                    "has_referer": bool(context.referer),
                    **context.extra,
                }
            },
        )

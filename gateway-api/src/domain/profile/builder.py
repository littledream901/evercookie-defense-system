"""从上下文构建设备/IP 画像快照。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from fangyu_shared.schemas.decision import DecisionContext
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile

from src.infrastructure.intel import IntelHit
from src.infrastructure.ua.parser import UAParser, UAResult


@dataclass(slots=True)
class ProfileSnapshot:
    """一次决策所需的画像视图。"""

    device: DeviceProfile
    ip: IpProfile
    ua: UAResult | None = None
    intel: IntelHit | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_evaluation_context(self) -> dict[str, Any]:
        """展开为规则条件可引用的扁平命名空间。

        规则 field 支持的顶层命名空间：
          device.*   设备画像（历史统计、信誉分）
          ip.*       IP 画像（地理、ASN、网络类型）
          ua.*       UA 解析结果（设备类型、OS、客户端、爬虫分类）
          intel.*    后台维护的六类维度情报命中结果
          request.*  本次请求实时属性
        """
        # mode="json" 让 datetime 序列化为 ISO 字符串。否则时间字段是 datetime
        # 对象，contains/startswith/regex 等字符串算子对其必然返回 False。
        return {
            "device": self.device.model_dump(by_alias=True, mode="json"),
            "ip": self.ip.model_dump(by_alias=True, mode="json"),
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
        intel: IntelHit | None = None,
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

        # 后台情报是 MMDB 的覆盖层：人工维护的结论优先于库文件解析
        if intel is not None and intel.ip_overrides:
            ip = ip.model_copy(update=intel.ip_overrides)

        ua = self._ua_parser.parse(context.user_agent)
        # 后台录入的爬虫特征覆盖内置签名表。parse 结果带 lru_cache，
        # 必须用 replace 产生副本，不能就地改动缓存实例。
        if intel is not None and intel.crawler_category and ua is not None:
            ua = replace(
                ua,
                crawler_category=intel.crawler_category,
                crawler_vendor=intel.crawler_name or ua.crawler_vendor,
                is_bot=True,
            )

        return ProfileSnapshot(
            device=device,
            ip=ip,
            ua=ua,
            intel=intel,
            context={
                "intel": {
                    "matched": intel.matched if intel else False,
                    "risk_score": intel.risk_score if intel else 0,
                    "reasons": list(intel.reasons) if intel else [],
                    "crawler_category": intel.crawler_category if intel else None,
                    "crawler_name": intel.crawler_name if intel else None,
                    "is_legitimate_crawler": intel.is_legitimate_crawler if intel else False,
                },
                # extra 来自客户端，必须先展开再写固定键，否则客户端可通过
                # extra={"path": "/safe"} 覆盖真实路径，让所有路径类规则失效。
                "request": {
                    **context.extra,
                    "path": context.path,
                    "method": context.method,
                    "user_agent": context.user_agent,
                    "referer": context.referer,
                    "session_id": context.session_id,
                    "has_referer": bool(context.referer),
                }
            },
        )

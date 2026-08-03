"""App 领域实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ApplicationStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


@dataclass(slots=True)
class Application:
    id: int | None
    site_id: str
    """站点唯一标识，格式 site_<hex8>，创建时服务端生成，不可修改。
    
    同时作为 X-App-Key 请求头的值，兼任 API Key 角色，
    无需再维护独立的 app_id 字段。
    """
    name: str
    domain: str
    """主域名，创建后不可修改，用作站点业务标识。"""
    app_secret: str = ""
    """HMAC 验签密钥，明文回显，可随时查看。"""
    alt_domains: list[str] = field(default_factory=list)
    access_mode: str = "adapter"
    """接入模式，与决策请求的 ingress 维度一一对应：

    - ``adapter``：服务端适配器（Nginx-Lua / WordPress 插件 / CF Worker / 直接 API），
      由站点服务端携带 App Secret 签名调用，指纹由网关按 IP+UA 派生。
    - ``sdk``：浏览器 SDK 埋码，由前端采集 Evercookie 指纹后调用。
    """
    sdk_version: str | None = None
    gateway_url: str | None = None
    """站点专属网关地址；留空则用部署级默认网关。"""
    is_active: bool = True
    owner_user_id: int | None = None
    clock_stats_enabled: bool = True
    log_retention_days: int = 30
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def status(self) -> ApplicationStatus:
        return ApplicationStatus.ACTIVE if self.is_active else ApplicationStatus.PAUSED

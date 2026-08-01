"""设备与 IP 画像 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from fangyu_shared.schemas.common import BaseSchema


class DeviceProfile(BaseSchema):
    """设备画像，缓存在 Redis Hash。"""

    fingerprint: str
    device_id: str | None = Field(default=None, alias="deviceId")
    first_seen_at: datetime = Field(default_factory=datetime.utcnow, alias="firstSeenAt")
    last_seen_at: datetime = Field(default_factory=datetime.utcnow, alias="lastSeenAt")
    total_requests: int = Field(default=0, alias="totalRequests")
    blocked_requests: int = Field(default=0, alias="blockedRequests")
    reputation_score: float = Field(default=50.0, alias="reputationScore", ge=0.0, le=100.0)
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class IpProfile(BaseSchema):
    """IP 画像。"""

    ip: str
    ip_type: str = Field(default="ipv4", alias="ipType")
    continent: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    asn: int | None = None
    asn_org: str | None = Field(default=None, alias="asnOrg")
    isp: str | None = None
    connection_type: str = Field(default="unknown", alias="connectionType")
    is_proxy: bool = Field(default=False, alias="isProxy")
    is_vpn: bool = Field(default=False, alias="isVpn")
    is_tor: bool = Field(default=False, alias="isTor")
    is_datacenter: bool = Field(default=False, alias="isDatacenter")
    is_mobile_network: bool = Field(default=False, alias="isMobileNetwork")
    reputation_score: float = Field(default=50.0, alias="reputationScore", ge=0.0, le=100.0)
    total_requests: int = Field(default=0, alias="totalRequests")
    last_seen_at: datetime = Field(default_factory=datetime.utcnow, alias="lastSeenAt")

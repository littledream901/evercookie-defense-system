"""设备/IP 画像缓存（共享实现）。

Gateway 读写；reputation 回流任务写；admin-api 手动同步时写。
键格式：
  IP    fangyu:profile:ip:{app_id}:{sha256_hex(ip)[:16]}
  设备  fangyu:profile:device:{app_id}:{fingerprint}

为什么 IP 键也带 app_id
-----------------------
声誉分是按「本站点观测到的拦截率」算出来的结论，不是 IP 的客观属性。不带
app_id 时所有租户共享同一条记录：A 站的爬虫流量会压低 B 站对同一 IP 的评分，
而 B 站可能压根没被这个 IP 骚扰过——既是多租户隔离破损，也让运营无法解释
「为什么这个正常访客的信誉分是 12」。设备画像本来就按 app_id 分键，IP 侧对齐。

跨租户的客观属性（Tor/VPN/数据中心网段）走情报库那条路（``fangyu:intel:*``），
与本缓存无关。
"""

from __future__ import annotations

import orjson
from redis.asyncio import Redis

from fangyu_shared.schemas.profile import DeviceProfile, IpProfile
from fangyu_shared.utils.crypto import sha256_hex

_DEVICE_PREFIX = "fangyu:profile:device"
_IP_PREFIX = "fangyu:profile:ip"


class ProfileCache:
    def __init__(self, redis: Redis, *, ttl: int = 3600) -> None:
        self._redis = redis
        self._ttl = ttl

    async def get_device(self, app_id: int, fingerprint: str) -> DeviceProfile | None:
        key = f"{_DEVICE_PREFIX}:{app_id}:{fingerprint}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            return DeviceProfile.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValueError):
            return None

    async def set_device(self, app_id: int, profile: DeviceProfile) -> None:
        key = f"{_DEVICE_PREFIX}:{app_id}:{profile.fingerprint}"
        await self._redis.set(
            key,
            orjson.dumps(profile.model_dump(by_alias=True, mode="json")),
            ex=self._ttl,
        )

    async def get_ip(self, app_id: int, ip: str) -> IpProfile | None:
        raw = await self._redis.get(self._ip_key(app_id, ip))
        if not raw:
            return None
        try:
            return IpProfile.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValueError):
            return None

    async def set_ip(self, app_id: int, profile: IpProfile) -> None:
        await self._redis.set(
            self._ip_key(app_id, profile.ip),
            orjson.dumps(profile.model_dump(by_alias=True, mode="json")),
            ex=self._ttl,
        )

    @staticmethod
    def _ip_key(app_id: int, ip: str) -> str:
        """IP 取 sha256 前 16 位而非原文：避免在 Redis 键名里留下明文 IP。"""
        return f"{_IP_PREFIX}:{app_id}:{sha256_hex(ip)[:16]}"

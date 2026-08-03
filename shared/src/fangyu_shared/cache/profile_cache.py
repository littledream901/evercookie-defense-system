"""设备/IP 画像缓存（共享实现）。

Gateway 读写；reputation_writer 写；admin-api 手动同步时写。
键格式：
  IP    fangyu:profile:ip:{sha256_hex(ip)[:16]}
  设备  fangyu:profile:device:{app_id}:{fingerprint}
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

    async def get_ip(self, ip: str) -> IpProfile | None:
        key = f"{_IP_PREFIX}:{sha256_hex(ip)[:16]}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            return IpProfile.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValueError):
            return None

    async def set_ip(self, profile: IpProfile) -> None:
        key = f"{_IP_PREFIX}:{sha256_hex(profile.ip)[:16]}"
        await self._redis.set(
            key,
            orjson.dumps(profile.model_dump(by_alias=True, mode="json")),
            ex=self._ttl,
        )

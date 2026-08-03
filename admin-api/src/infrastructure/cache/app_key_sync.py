"""app_key ↔ app_id 的 Redis 同步器。

admin-api 是 app / api_key 唯一的写入方，gateway 只读取。所以映射由
admin 侧在下列操作时同步：

- 创建应用：``bind(app.api_key, app.id, app.app_secret)``
- 轮换 API Key：先 ``unbind(旧 key)`` 再 ``bind(新 key)``
- 删除应用：``unbind(api_key)``

Redis 键位：``fangyu:app_keys:{api_key}`` → ``{"app_id": 1, "app_secret": "..."}``

为什么写 JSON 而不是裸 app_id
-----------------------------
gateway 验签需要 app_secret，而它不连 MySQL——只能从这条映射里拿。写成 JSON
后 gateway 一次 Redis GET 同时得到身份与密钥，无需额外键或跨库查询。
gateway 侧仍兼容裸 app_id 的旧值，滚动升级期间不会中断。
"""

from __future__ import annotations

from typing import Any

import orjson

from fangyu_shared.logging import get_logger

_logger = get_logger("admin.app_key_sync")


class AppKeyRedisSync:
    """把 api_key ↔ app_id 映射同步到 Redis。"""

    def __init__(
        self,
        redis: Any,
        *,
        key_prefix: str = "fangyu:app_keys:",
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix
        self._ttl = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None

    def _redis_key(self, api_key: str) -> str:
        return f"{self._prefix}{api_key}"

    async def bind(self, api_key: str, app_id: int, app_secret: str | None = None) -> None:
        if not api_key or app_id <= 0:
            return
        payload: dict[str, Any] = {"app_id": app_id}
        if app_secret:
            payload["app_secret"] = app_secret
        value = orjson.dumps(payload).decode()
        try:
            if self._ttl:
                await self._redis.set(self._redis_key(api_key), value, ex=self._ttl)
            else:
                await self._redis.set(self._redis_key(api_key), value)
        except Exception as exc:  # pragma: no cover - Redis 异常不阻断业务
            _logger.error("app_key_bind_failed", app_id=app_id, error=str(exc))

    async def unbind(self, api_key: str) -> None:
        if not api_key:
            return
        try:
            await self._redis.delete(self._redis_key(api_key))
        except Exception as exc:  # pragma: no cover
            _logger.error("app_key_unbind_failed", key_prefix=api_key[:6], error=str(exc))

    async def rebind(
        self,
        old_key: str | None,
        new_key: str,
        app_id: int,
        app_secret: str | None = None,
    ) -> None:
        if old_key and old_key != new_key:
            await self.unbind(old_key)
        await self.bind(new_key, app_id, app_secret)


__all__ = ["AppKeyRedisSync"]

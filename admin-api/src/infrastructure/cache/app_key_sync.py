"""app_key ↔ app_id 的 Redis 同步器。

admin-api 是 app / api_key 唯一的写入方，gateway 只读取。所以映射由
admin 侧在下列操作时同步：

- 创建应用：``bind(app.api_key, app.id, app.app_secret)``
- 轮换 API Key：先 ``unbind(旧 key)`` 再 ``bind(新 key)``
- 删除应用：``unbind(api_key)``

Redis 键位：
- 正向 ``fangyu:app_keys:{api_key}`` → ``{"app_id": 1, "app_secret": "..."}``
- 反向 ``fangyu:app_secrets:{app_id}`` → ``app_secret``（供 challenge token 签发按
  app_id 反查，正向键无法按 app_id 检索）

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
        secret_prefix: str = "fangyu:app_secrets:",
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix
        self._secret_prefix = secret_prefix
        self._ttl = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None

    def _redis_key(self, api_key: str) -> str:
        return f"{self._prefix}{api_key}"

    def _secret_key(self, app_id: int) -> str:
        return f"{self._secret_prefix}{app_id}"

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

        # 反向索引：challenge token 签发需按 app_id 取 secret，而正向键以 api_key
        # 作后缀无法反查。缺这条索引时 gateway 只能扫本地缓存，多 worker 部署下
        # 处理 verify 的进程往往不是处理 decide 的那个，挑战会静默失败。
        if not app_secret:
            return
        try:
            if self._ttl:
                await self._redis.set(self._secret_key(app_id), app_secret, ex=self._ttl)
            else:
                await self._redis.set(self._secret_key(app_id), app_secret)
        except Exception as exc:  # pragma: no cover
            _logger.error("app_secret_index_failed", app_id=app_id, error=str(exc))

    async def unbind(self, api_key: str, app_id: int | None = None) -> None:
        if not api_key:
            return
        try:
            await self._redis.delete(self._redis_key(api_key))
        except Exception as exc:  # pragma: no cover
            _logger.error("app_key_unbind_failed", key_prefix=api_key[:6], error=str(exc))

        # 轮换 API Key 时不能删反向索引：secret 未变，且 rebind 紧接着会重写。
        # 只有删除应用（显式传 app_id）才清理。
        if app_id is None or app_id <= 0:
            return
        try:
            await self._redis.delete(self._secret_key(app_id))
        except Exception as exc:  # pragma: no cover
            _logger.error("app_secret_index_unbind_failed", app_id=app_id, error=str(exc))

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

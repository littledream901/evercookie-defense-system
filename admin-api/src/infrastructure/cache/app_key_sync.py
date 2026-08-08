"""site_key ↔ site_id 的 Redis 同步器。

admin-api 是站点/API Key 唯一的写入方，gateway 只读取。所以映射由
admin 侧在下列操作时同步：

- 创建站点：``bind(site.site_key, site.id, site.site_secret)``
- 轮换 API Key：先 ``unbind(旧 key)`` 再 ``bind(新 key)``
- 删除站点：``unbind(site_key)``

Redis 键位：
- 正向 ``fangyu:app_keys:{site_key}`` → ``{"app_id": <site_id>, "app_secret": "..."}``
  （注：JSON 字段名 app_id 是历史遗留，值是站点 ID）
- 反向 ``fangyu:app_secrets:{site_id}`` → ``site_secret``（供 challenge token 签发按
  site_id 反查，正向键无法按 site_id 检索）

注：正向键前缀保持 app_keys 是历史遗留，实际值是站点 ID（Site.id）而非应用 ID。

为什么写 JSON 而不是裸 site_id
-----------------------------
gateway 验签需要 site_secret，而它不连 MySQL——只能从这条映射里拿。写成 JSON
后 gateway 一次 Redis GET 同时得到身份与密钥，无需额外键或跨库查询。
"""

from __future__ import annotations

from typing import Any

import orjson

from fangyu_shared.logging import get_logger

_logger = get_logger("admin.app_key_sync")


class AppKeyRedisSync:
    """把 api_key ↔ site_id 映射同步到 Redis。
    
    注：类名保持 AppKey 是历史遗留，实际处理的是站点 ID（Site.id）。
    """

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

    def _secret_key(self, site_id: int) -> str:
        return f"{self._secret_prefix}{site_id}"

    async def bind(self, api_key: str, site_id: int, app_secret: str | None = None) -> None:
        if not api_key or site_id <= 0:
            return
        payload: dict[str, Any] = {"app_id": site_id}
        if app_secret:
            payload["app_secret"] = app_secret
        value = orjson.dumps(payload).decode()
        try:
            if self._ttl:
                await self._redis.set(self._redis_key(api_key), value, ex=self._ttl)
            else:
                await self._redis.set(self._redis_key(api_key), value)
        except Exception as exc:  # pragma: no cover - Redis 异常不阻断业务
            _logger.error("app_key_bind_failed", site_id=site_id, error=str(exc))

        # 反向索引：challenge token 签发需按 site_id 取 secret，而正向键以 api_key
        # 作后缀无法反查。缺这条索引时 gateway 只能扫本地缓存，多 worker 部署下
        # 处理 verify 的进程往往不是处理 decide 的那个，挑战会静默失败。
        if not app_secret:
            return
        try:
            if self._ttl:
                await self._redis.set(self._secret_key(site_id), app_secret, ex=self._ttl)
            else:
                await self._redis.set(self._secret_key(site_id), app_secret)
        except Exception as exc:  # pragma: no cover
            _logger.error("app_secret_index_failed", site_id=site_id, error=str(exc))

    async def unbind(self, site_key: str, site_id: int | None = None) -> None:
        """解绑 site_key，同时清除正向与反向索引。

        Args:
            site_key: 待解绑的站点密钥
            site_id: 站点ID，若提供则同时清除反向索引
        """
        if not site_key:
            return
        try:
            await self._redis.delete(self._redis_key(site_key))
        except Exception as exc:  # pragma: no cover
            _logger.error("site_key_unbind_failed", site_key=site_key, error=str(exc))

        # 轮换 API Key 时不能删反向索引：secret 未变，且 rebind 紧接着会重写。
        # 只有删除应用（显式传 site_id）才清理。
        if site_id is None or site_id <= 0:
            return
        try:
            await self._redis.delete(self._secret_key(site_id))
        except Exception as exc:  # pragma: no cover
            _logger.error("site_secret_index_delete_failed", site_id=site_id, error=str(exc))

    async def rebind(
        self,
        old_key: str | None,
        new_key: str,
        site_id: int,
        app_secret: str | None = None,
    ) -> None:
        if old_key and old_key != new_key:
            await self.unbind(old_key)
        await self.bind(new_key, site_id, app_secret)


__all__ = ["AppKeyRedisSync"]

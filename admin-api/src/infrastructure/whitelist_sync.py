"""白名单的 Redis 写入面。

键格式与序列化形状复用 :mod:`fangyu_shared.whitelist.keys`，不手写字符串
拼接——与 :mod:`src.infrastructure.clock_sync` 同样的理由：V1 出现过 admin
写一个前缀、gateway 读另一个前缀，配置写了但永不生效且日志无异常。

**刻意不设 TTL**。白名单是配置不是缓存，过期后无人重建会让被误封的访客
再次被拦，而且没有任何报错提示。代价是 Redis flush 后需要人工重录——
参见 :meth:`WhitelistSync.list_entries` 上方关于持久化的说明。
"""

from __future__ import annotations

from typing import Any

import orjson
from fangyu_shared.utils.time import utcnow_ms
from fangyu_shared.whitelist.keys import (
    WhitelistDimension,
    field_name,
    parse_field,
    whitelist_key,
)
from redis.asyncio import Redis


class WhitelistSync:
    """app 级白名单的 Redis 读写。

    白名单只存 Redis，没有 DB 表。这是计划限定的范围（`fangyu:whitelist:
    {app_id}`），也是白名单与频控阈值的关键差别：阈值有默认值兜底，丢了只是
    回到默认防护；白名单丢了没有任何兜底。因此 Redis 持久化配置（AOF/RDB）
    是这个功能的前提，运维文档里要写明。
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def add(
        self,
        app_id: int,
        dimension: WhitelistDimension,
        value: str,
        *,
        note: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        """新增或覆盖一条白名单。

        幂等覆盖而非拒绝重复：运维重复提交同一个 IP 时报错没有意义，更新备注
        反而是更常见的真实意图。
        """
        now_ms = utcnow_ms()
        meta = {"note": note, "createdBy": created_by, "createdAtMs": now_ms}
        await self._redis.hset(  # type: ignore[misc]
            whitelist_key(app_id), field_name(dimension, value), orjson.dumps(meta)
        )
        return {
            "dimension": dimension.value,
            "value": value,
            "note": note,
            "createdBy": created_by,
            "createdAtMs": now_ms,
        }

    async def remove(
        self, app_id: int, dimension: WhitelistDimension, value: str
    ) -> bool:
        """删除一条。返回是否确实删掉了（用于区分 404）。"""
        removed = await self._redis.hdel(  # type: ignore[misc]
            whitelist_key(app_id), field_name(dimension, value)
        )
        return bool(removed)

    async def get(
        self, app_id: int, dimension: WhitelistDimension, value: str
    ) -> dict[str, Any] | None:
        """查询单条。不存在返回 ``None``。"""
        raw = await self._redis.hget(  # type: ignore[misc]
            whitelist_key(app_id), field_name(dimension, value)
        )
        if raw is None:
            return None
        return _entry(dimension, value, raw)

    async def list_entries(self, app_id: int) -> list[dict[str, Any]]:
        """列出某 app 的全部白名单。

        用 ``HGETALL`` 而不是 ``HSCAN``：白名单是人工维护的准入清单，量级在
        几十到几百条，一次取回比游标分页简单得多。这个前提由写入侧的
        :data:`MAX_ENTRIES_PER_APP` 保证——不设上限的话，某天有人脚本批量灌
        十万条，这里就会阻塞 Redis。
        """
        raw_map = await self._redis.hgetall(whitelist_key(app_id))  # type: ignore[misc]
        out: list[dict[str, Any]] = []
        for field, raw in (raw_map or {}).items():
            parsed = parse_field(_text(field))
            if parsed is None:
                # 脏 field 跳过而不报错，否则运维连删掉它的列表页都打不开
                continue
            dimension, value = parsed
            out.append(_entry(dimension, value, raw))
        out.sort(key=lambda e: (e["dimension"], e["value"]))
        return out

    async def count(self, app_id: int) -> int:
        """当前条目数。写入前做上限校验用。"""
        return int(await self._redis.hlen(whitelist_key(app_id)))  # type: ignore[misc]

    async def clear(self, app_id: int) -> int:
        """清空某 app 的白名单，返回删除条数。"""
        key = whitelist_key(app_id)
        size = int(await self._redis.hlen(key))  # type: ignore[misc]
        if size:
            await self._redis.delete(key)
        return size


def _entry(
    dimension: WhitelistDimension, value: str, raw: object
) -> dict[str, Any]:
    """把 Hash field/value 还原成 wire 形状。

    元信息解析失败时退化成空备注，而不是抛异常——条目本身的存在性是主要
    信息，坏掉的备注不该让整个列表接口 500。
    """
    meta: dict[str, Any] = {}
    if raw:
        try:
            loaded = orjson.loads(raw)
        except (orjson.JSONDecodeError, TypeError, ValueError):
            loaded = None
        if isinstance(loaded, dict):
            meta = loaded
    return {
        "dimension": dimension.value,
        "value": value,
        "note": str(meta.get("note", "")),
        "createdBy": str(meta.get("createdBy", "")),
        "createdAtMs": int(meta.get("createdAtMs", 0) or 0),
    }


def _text(field: object) -> str:
    """Hash field 可能是 bytes（未开 decode_responses）或 str。"""
    if isinstance(field, bytes):
        return field.decode("utf-8", errors="replace")
    return str(field)

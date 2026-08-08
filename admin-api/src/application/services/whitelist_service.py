"""白名单编排服务。

与 ``ClockService`` 不同，这里没有「先落库再同步 Redis」的两段写：白名单
只存 Redis（计划限定范围）。因此本服务的职责集中在**写入前的校验**——
白名单绕过全部风控，一条错误条目的代价远高于一条错误频控阈值。
"""

from __future__ import annotations

import ipaddress
from typing import Any

from fangyu_shared.whitelist.keys import WhitelistDimension

from src.infrastructure.whitelist_sync import WhitelistSync

MAX_ENTRIES_PER_APP = 500
"""单 app 白名单条数上限。

上限存在的理由不是存储成本，而是 ``list_entries`` 走 ``HGETALL``：无上限时
批量灌入会让列表接口阻塞 Redis。500 条对人工维护的准入清单足够宽松；真要
放行大批量流量，那是决策规则 allowlist 组该解决的问题。
"""

MAX_FINGERPRINT_LEN = 128


class WhitelistError(ValueError):
    """白名单校验失败。由路由层转成 400。"""


class WhitelistService:
    def __init__(self, sync: WhitelistSync) -> None:
        self._sync = sync

    async def add(
        self,
        site_id: int,
        dimension: WhitelistDimension,
        value: str,
        *,
        note: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        """新增一条白名单。

        校验顺序：先规范化值，再查上限。反过来的话，一个非法 IP 也会先付出
        一次 ``HLEN`` 往返。
        """
        normalized = self._normalize(dimension, value)

        # 已存在的条目属于「改备注」，不占新配额，否则满额后连备注都改不了
        existing = await self._sync.get(site_id, dimension, normalized)
        if existing is None and await self._sync.count(site_id) >= MAX_ENTRIES_PER_APP:
            raise WhitelistError(
                f"白名单条目已达上限 {MAX_ENTRIES_PER_APP}，请先清理无用条目"
            )

        return await self._sync.add(
            site_id, dimension, normalized, note=note, created_by=created_by
        )

    async def remove(
        self, site_id: int, dimension: WhitelistDimension, value: str
    ) -> bool:
        """删除一条。值同样先规范化，否则 ``1.2.3.004`` 这类写法删不掉。"""
        return await self._sync.remove(
            site_id, dimension, self._normalize(dimension, value)
        )

    async def list_entries(self, site_id: int) -> list[dict[str, Any]]:
        return await self._sync.list_entries(site_id)

    async def clear(self, site_id: int) -> int:
        return await self._sync.clear(site_id)

    @staticmethod
    def _normalize(dimension: WhitelistDimension, value: str) -> str:
        """规范化并校验值。

        IP 走 ``ipaddress`` 解析后取压缩表示。这一步是必须的：gateway 侧用
        ``str(ctx.ip)`` 查表，那是 pydantic ``IPvAnyAddress`` 的压缩形式。若
        admin 原样存下 ``::FFFF:1.2.3.4`` 或 ``1.2.3.004``，字段名对不上，
        白名单写了但永不命中——而且没有任何报错。

        指纹不做格式约束（采集端算法可能演进），只查长度与空白。
        """
        stripped = value.strip()
        if not stripped:
            raise WhitelistError("白名单值不能为空")

        if dimension is WhitelistDimension.IP:
            try:
                return str(ipaddress.ip_address(stripped))
            except ValueError as exc:
                raise WhitelistError(f"非法 IP 地址: {value}") from exc

        if len(stripped) > MAX_FINGERPRINT_LEN:
            raise WhitelistError(f"指纹长度超过 {MAX_FINGERPRINT_LEN}")
        return stripped

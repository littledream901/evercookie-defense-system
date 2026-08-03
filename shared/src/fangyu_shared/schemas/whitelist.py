"""白名单的 wire 契约。

领域词汇（维度、键构造）在 :mod:`fangyu_shared.whitelist`，本模块只负责
pydantic 形状——与 clock 的分层方式一致。
"""

from __future__ import annotations

from pydantic import Field

from fangyu_shared.schemas.common import BaseSchema
from fangyu_shared.whitelist.keys import WhitelistDimension


class WhitelistEntry(BaseSchema):
    """一条白名单记录。

    ``note`` / ``created_by`` 不是装饰性字段。白名单绕过全部风控，是系统里
    最危险的配置项；缺少「谁为什么加的」这两条信息时，接手的人无法判断某条
    是否还该留着，最终只能整表清空重来。
    """

    dimension: WhitelistDimension
    value: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=256)
    created_by: str = Field(default="", alias="createdBy", max_length=64)
    created_at_ms: int = Field(default=0, alias="createdAtMs", ge=0)

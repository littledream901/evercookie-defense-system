"""白名单领域词汇：键构造与维度。

与 :mod:`fangyu_shared.clock` 并列而非塞进去，因为白名单不属于频控：它跨越
整条流水线（频控、威胁情报、安全检查、评分全部跳过），语义上是「这条流量
不参与风控」，而 clock 包只描述计数窗口。
"""

from __future__ import annotations

from fangyu_shared.whitelist.keys import (
    WhitelistDimension,
    field_name,
    parse_field,
    whitelist_key,
)

__all__ = [
    "WhitelistDimension",
    "field_name",
    "parse_field",
    "whitelist_key",
]

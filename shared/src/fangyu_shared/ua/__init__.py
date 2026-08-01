"""User-Agent 解析（纯正则，零外部依赖）。

放在 shared 而不是 gateway，是因为 admin 的规则试跑接口也需要用同一份解析结果，
否则后台预览看到的 ua.* 字段与线上决策不一致。
"""

from fangyu_shared.ua.crawlers import (
    CRAWLER_CATEGORIES,
    CRAWLER_VENDORS,
    CrawlerSignature,
    match_crawler,
)
from fangyu_shared.ua.parser import (
    CLIENT_TYPES,
    DEVICE_TYPES,
    UAParser,
    UAResult,
    parse_user_agent,
)

__all__ = [
    "CLIENT_TYPES",
    "CRAWLER_CATEGORIES",
    "CRAWLER_VENDORS",
    "DEVICE_TYPES",
    "CrawlerSignature",
    "UAParser",
    "UAResult",
    "match_crawler",
    "parse_user_agent",
]

"""UA 解析已迁移到 fangyu_shared.ua，此处保留以向后兼容。"""

from fangyu_shared.ua import (
    CLIENT_TYPES,
    CRAWLER_CATEGORIES,
    CRAWLER_VENDORS,
    DEVICE_TYPES,
    CrawlerSignature,
    UAParser,
    UAResult,
    match_crawler,
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

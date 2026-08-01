"""Admin 侧缓存。"""

from __future__ import annotations

from src.infrastructure.cache.permission_cache import PermissionCache
from src.infrastructure.cache.rule_cache import RuleCache

__all__ = ["PermissionCache", "RuleCache"]

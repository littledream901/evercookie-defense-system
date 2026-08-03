"""fangyu_shared.cache — Redis 缓存层（供 gateway / worker / admin 共用）。"""

from __future__ import annotations

from fangyu_shared.cache.profile_cache import ProfileCache

__all__ = ["ProfileCache"]

"""設備/IP 画像缓存（re-export from shared）。

保持原有导入路径不变，供 gateway 内部代码直接使用。
"""

from __future__ import annotations

from fangyu_shared.cache.profile_cache import ProfileCache

__all__ = ["ProfileCache"]

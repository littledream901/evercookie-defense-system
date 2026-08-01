"""admin-api 单元测试的 sys.path 与模块隔离。

由于 admin-api 与 gateway-api 都以 `src` 作为顶层包名，同一 pytest 进程内
如果同时加载两者，后加载的模块会污染前者。所以本 conftest 在会话开始时
清空已经缓存的 `src.*` 模块，并把 admin-api 顶层目录插到 sys.path 最前面。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ADMIN = Path(__file__).resolve().parents[2] / "admin-api"

# 移除其他服务残留的 src.* 缓存
for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)

# 移除其他服务的 admin-api 兄弟目录，避免解析错误
_other_roots = {
    str(_ADMIN.parent / name)
    for name in ("gateway-api", "worker")
}
sys.path[:] = [p for p in sys.path if p not in _other_roots]

if _ADMIN.exists() and str(_ADMIN) not in sys.path:
    sys.path.insert(0, str(_ADMIN))

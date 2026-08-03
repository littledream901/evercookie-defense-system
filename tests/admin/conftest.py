"""admin-api 单元测试的 sys.path 与模块隔离。

由于 admin-api 与 gateway-api 都以 `src` 作为顶层包名，同一 pytest 进程内
如果同时加载两者，后加载的模块会污染前者。本 conftest 在会话开始时
清空已经缓存的 `src.*` 模块，并把 admin-api 顶层目录插到 sys.path 最前面。
autouse fixture 在每个测试函数执行前再次确认 sys.path 正确（防止 gateway
conftest 的模块级代码把 admin-api 从 sys.path 中移除）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ADMIN = Path(__file__).resolve().parents[2] / "admin-api"

_other_roots = {
    str(_ADMIN.parent / name)
    for name in ("gateway-api", "worker")
}

# Module-level setup (collection time)
for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)
sys.path[:] = [p for p in sys.path if p not in _other_roots]
if _ADMIN.exists() and str(_ADMIN) not in sys.path:
    sys.path.insert(0, str(_ADMIN))


@pytest.fixture(autouse=True)
def _admin_service_path() -> None:
    """Re-establish admin-api sys.path before every test in this directory.

    Needed when gateway tests run in the same session: their conftest (and the
    root pytest_pycollect_makemodule hook) may have left gateway-api on sys.path.
    Any lazy ``from src.xxx import yyy`` inside a test function body will then
    resolve to the correct admin package.
    """
    for _m in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
        sys.modules.pop(_m, None)
    sys.path[:] = [p for p in sys.path if p not in _other_roots]
    if str(_ADMIN) not in sys.path:
        sys.path.insert(0, str(_ADMIN))

"""V2 全局测试配置：只把 shared 加到 sys.path。

因 admin-api 与 gateway-api 都以 `src` 作为顶层包名，二者不能同时进入 sys.path。
子目录 conftest 通过 autouse fixture 在每个测试执行前切换 sys.path；
根 conftest 中的 pytest_pycollect_makemodule 钩子在每个测试文件被导入前正确切换
sys.path，确保模块级 `from src.xxx import yyy` 也能找到正确的包。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SHARED = _ROOT / "shared" / "src"
if _SHARED.exists() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# ---------------------------------------------------------------------------
# Per-file sys.path switching — runs right before each test module is imported
# ---------------------------------------------------------------------------
_SERVICE_ROOTS: dict[str, Path] = {
    "admin": _ROOT / "admin-api",
    "gateway": _ROOT / "gateway-api",
    "worker": _ROOT / "worker",
}
_ALL_ROOTS = set(_SERVICE_ROOTS.values())


def _switch_service(service_root: Path) -> None:
    """Point sys.path at *service_root*, evicting all other service roots."""
    for m in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
        sys.modules.pop(m, None)
    sys.path[:] = [p for p in sys.path if Path(p) not in _ALL_ROOTS]
    root_str = str(service_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def pytest_pycollect_makemodule(module_path, path, parent):  # noqa: ARG001
    """Switch sys.path to the right service before each test module is imported.

    pytest calls this hook just before importing a test ``.py`` file for
    collection.  By inspecting the file path we can ensure the correct ``src``
    package is visible when the module's top-level imports execute.
    """
    mp = str(module_path).replace("\\", "/")
    for subdir, root in _SERVICE_ROOTS.items():
        if f"/tests/{subdir}/" in mp:
            _switch_service(root)
            break
    return None  # use default Module collector

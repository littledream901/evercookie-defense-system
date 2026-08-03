"""gateway-api 单元测试的 sys.path 与模块隔离。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_GATEWAY = Path(__file__).resolve().parents[2] / "gateway-api"

_other_roots = {
    str(_GATEWAY.parent / name)
    for name in ("admin-api", "worker")
}

# Module-level setup (collection time — acts as a first-pass guard when only
# gateway tests are collected directly).
for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)
sys.path[:] = [p for p in sys.path if p not in _other_roots]
if _GATEWAY.exists() and str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))


@pytest.fixture(autouse=True)
def _gateway_service_path() -> None:
    """Re-establish gateway-api sys.path before every test in this directory.

    Needed when admin tests run in the same session: their conftest (and the
    root pytest_pycollect_makemodule hook) may have left admin-api on sys.path.
    Any lazy ``from src.xxx import yyy`` inside a test function body will then
    resolve to the correct gateway package.
    """
    for _m in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
        sys.modules.pop(_m, None)
    sys.path[:] = [p for p in sys.path if p not in _other_roots]
    if str(_GATEWAY) not in sys.path:
        sys.path.insert(0, str(_GATEWAY))

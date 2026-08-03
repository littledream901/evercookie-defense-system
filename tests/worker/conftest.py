"""worker 单元测试的 sys.path 与模块隔离。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_WORKER = Path(__file__).resolve().parents[2] / "worker"

_other_roots = {
    str(_WORKER.parent / name)
    for name in ("admin-api", "gateway-api")
}

# Module-level setup (collection time)
for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)
sys.path[:] = [p for p in sys.path if p not in _other_roots]
if _WORKER.exists() and str(_WORKER) not in sys.path:
    sys.path.insert(0, str(_WORKER))


@pytest.fixture(autouse=True)
def _worker_service_path() -> None:
    """Re-establish worker sys.path before every test in this directory."""
    for _m in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
        sys.modules.pop(_m, None)
    sys.path[:] = [p for p in sys.path if p not in _other_roots]
    if str(_WORKER) not in sys.path:
        sys.path.insert(0, str(_WORKER))

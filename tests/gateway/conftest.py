"""gateway-api 单元测试的 sys.path 与模块隔离。"""
from __future__ import annotations

import sys
from pathlib import Path

_GATEWAY = Path(__file__).resolve().parents[2] / "gateway-api"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_name, None)

_other_roots = {
    str(_GATEWAY.parent / name)
    for name in ("admin-api", "worker")
}
sys.path[:] = [p for p in sys.path if p not in _other_roots]

if _GATEWAY.exists() and str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))

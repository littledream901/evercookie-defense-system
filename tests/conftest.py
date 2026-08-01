"""V2 全局测试配置：只把 shared 加到 sys.path。

因 admin-api 与 gateway-api 都以 `src` 作为顶层包名，二者不能同时进入 sys.path。
各服务的测试子目录内会设置自己的 sys.path。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SHARED = _ROOT / "shared" / "src"
if _SHARED.exists() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

"""复现 admin-api 的 500 错误并打印完整堆栈。

线上实例把未捕获异常统一包装成 ``INTERNAL_UNKNOWN``，响应体里没有堆栈。
这里用 TestClient 直接跑同一个 app：``raise_server_exceptions=True``（默认）
会让 ServerErrorMiddleware 在生成响应后重新抛出原始异常，从而拿到真因。

用法（必须在 admin-api 目录下执行，否则读不到 .env）：
    cd admin-api && python ../tests/api/test_500_reproduction.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ADMIN_SRC = Path(__file__).resolve().parents[2] / "admin-api"
sys.path.insert(0, str(_ADMIN_SRC))

from fastapi.testclient import TestClient  # noqa: E402

from src.main import create_app  # noqa: E402

TARGETS: list[tuple[str, str, dict | None]] = [
    ("GET", "/v2/rules", None),
    ("GET", "/v2/sites/1/rules", None),
    ("GET", "/v2/clock/limits", None),
    ("GET", "/v2/page-resources", None),
    ("GET", "/v2/sites/1/integration-diagnostics", None),
    ("GET", "/v2/access-logs", None),
    ("GET", "/v2/access-logs/stats/summary", None),
    (
        "POST",
        "/v2/analytics/timeline",
        {
            "site_id": None,
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-08T00:00:00+00:00",
            "filters": {},
        },
    ),
]


def main() -> None:
    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/v2/auth/login",
            json={"username": "admin", "password": "Admin@fangyu2026"},
        )
        if resp.status_code != 200:
            raise SystemExit(f"登录失败 {resp.status_code}: {resp.text[:400]}")
        client.headers["Authorization"] = (
            f"Bearer {resp.json()['data']['tokens']['access_token']}"
        )

        for method, path, body in TARGETS:
            print("\n" + "=" * 78)
            print(f"### {method} {path}")
            print("=" * 78)
            try:
                r = client.request(method, path, json=body)
                print(f"HTTP {r.status_code}  {r.text[:300]}")
            except Exception as exc:  # noqa: BLE001 - 目的就是打印任意异常
                # 只打印项目自身代码的帧，滤掉 starlette/fastapi/anyio 的中间件栈，
                # 否则单个异常上百行输出会淹没真正的根因
                frames = [
                    f
                    for f in traceback.extract_tb(exc.__traceback__)
                    if "site-packages" not in f.filename and "Python314\\Lib" not in f.filename
                ]
                for f in frames:
                    print(f"  {f.filename}:{f.lineno} in {f.name}")
                    print(f"      {f.line}")
                print(f"  >>> {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

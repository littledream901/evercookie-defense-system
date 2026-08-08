"""Admin API 全量连通性探测。

以管理员账号登录后遍历 OpenAPI 中声明的所有端点，对**只读**操作（GET 与
分析类查询 POST）发起真实请求，汇总状态码并单独列出 5xx。

写操作（POST/PUT/PATCH/DELETE 的非白名单项）默认跳过，避免污染数据。

用法：
    python tests/api/test_admin_api_connectivity.py
环境变量（见 .env.example）：
    ADMIN_BASE_URL / ADMIN_BOOTSTRAP_USERNAME / ADMIN_BOOTSTRAP_PASSWORD
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

BASE_URL = os.getenv("ADMIN_BASE_URL", "http://127.0.0.1:8081")
USERNAME = os.getenv("ADMIN_BOOTSTRAP_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "Admin@fangyu2026")
TIMEOUT = float(os.getenv("ADMIN_PROBE_TIMEOUT", "20"))

# 只读 POST 白名单：纯查询语义，不产生副作用
READONLY_POST = {
    "/v2/analytics/timeline",
    "/v2/analytics/disposition-breakdown",
    "/v2/analytics/top-entities",
    "/v2/analytics/rule-hit-rate",
    "/v2/rules/preview",
}

_NOW = datetime.now(timezone.utc).replace(microsecond=0)
_START = _NOW - timedelta(days=7)

_ANALYTICS_BODY = {
    "site_id": None,
    "start": _START.isoformat(),
    "end": _NOW.isoformat(),
}

# 路径参数取值：site_id 等会在运行时用真实数据覆盖
PATH_DEFAULTS: dict[str, Any] = {
    "site_id": 1,
    "app_id": 1,
    "user_id": 1,
    "role_id": 1,
    "rule_id": 1,
    "resource_id": 1,
    "key_id": 1,
    "request_id": "probe-nonexistent-request-id",
    "intel_type": "ip",
    "preset_name": "probe-nonexistent-preset",
    "file_type": "country",
    "ip": "203.0.113.1",
}


def _body_for(path: str) -> dict[str, Any] | None:
    if path == "/v2/analytics/rule-hit-rate":
        return dict(_ANALYTICS_BODY)
    if path.startswith("/v2/analytics/"):
        return {**_ANALYTICS_BODY, "filters": {}}
    if path == "/v2/rules/preview":
        return {
            "conditions": {"op": "and", "children": []},
            "sample": {"ip": "203.0.113.1", "user_agent": "probe/1.0"},
        }
    return None


def _fill_path(path: str, overrides: dict[str, Any]) -> str:
    filled = path
    for name, value in {**PATH_DEFAULTS, **overrides}.items():
        filled = filled.replace("{" + name + "}", str(value))
    return filled


def _query_for(operation: dict[str, Any]) -> dict[str, Any]:
    """按 OpenAPI 声明补齐 required 的 query 参数，取 schema 默认值或类型兜底值。"""
    params: dict[str, Any] = {}
    for spec in operation.get("parameters", []):
        if spec.get("in") != "query" or not spec.get("required"):
            continue
        schema = spec.get("schema", {})
        name = spec["name"]
        if "default" in schema:
            params[name] = schema["default"]
        elif name in ("start", "start_time", "from"):
            params[name] = _START.isoformat()
        elif name in ("end", "end_time", "to"):
            params[name] = _NOW.isoformat()
        elif schema.get("type") == "integer":
            params[name] = 1
        else:
            params[name] = PATH_DEFAULTS.get(name, "probe")
    return params


def login(client: httpx.Client) -> str:
    resp = client.post(
        "/v2/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    if resp.status_code != 200:
        raise SystemExit(f"登录失败 HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()["data"]["tokens"]["access_token"]


def discover_ids(client: httpx.Client) -> dict[str, Any]:
    """抓一条真实的 site_id / app_id / rule_id，避免全部命中 404 掩盖真实错误。"""
    overrides: dict[str, Any] = {}
    for endpoint, key in (("/v2/sites", "site_id"), ("/v2/applications", "app_id")):
        try:
            resp = client.get(endpoint, params={"page": 1, "page_size": 1})
            items = (resp.json().get("data") or {}).get("items") or []
            if items:
                overrides[key] = items[0]["id"]
        except Exception:  # noqa: BLE001 - 探测失败不影响主流程
            continue
    return overrides


def probe_all(client: httpx.Client, overrides: dict[str, Any]) -> list[dict[str, Any]]:
    spec = client.get("/openapi.json").json()
    results: list[dict[str, Any]] = []
    for raw_path, methods in spec["paths"].items():
        for method, operation in methods.items():
            verb = method.upper()
            if verb != "GET" and raw_path not in READONLY_POST:
                results.append(
                    {
                        "method": verb,
                        "path": raw_path,
                        "status": None,
                        "note": "skipped: 写操作",
                    }
                )
                continue
            url = _fill_path(raw_path, overrides)
            try:
                resp = client.request(
                    verb,
                    url,
                    params=_query_for(operation) or None,
                    json=_body_for(raw_path),
                )
                body = resp.text
            except Exception as exc:  # noqa: BLE001 - 记录传输层失败
                results.append(
                    {
                        "method": verb,
                        "path": raw_path,
                        "status": None,
                        "note": f"transport error: {exc}",
                    }
                )
                continue
            results.append(
                {
                    "method": verb,
                    "path": raw_path,
                    "url": url,
                    "status": resp.status_code,
                    "body": body[:1500],
                }
            )
    return results


def report(results: list[dict[str, Any]]) -> int:
    probed = [r for r in results if r["status"] is not None]
    skipped = [r for r in results if r["status"] is None and "skipped" in (r.get("note") or "")]
    errors = [r for r in probed if r["status"] >= 500]

    buckets: dict[int, int] = {}
    for r in probed:
        buckets[r["status"]] = buckets.get(r["status"], 0) + 1

    print("=" * 78)
    print(f"探测端点 {len(probed)} 个，跳过写操作 {len(skipped)} 个")
    print("状态码分布：", dict(sorted(buckets.items())))
    print("=" * 78)

    for r in sorted(probed, key=lambda x: (-x["status"], x["path"])):
        flag = "FAIL" if r["status"] >= 500 else "ok  "
        print(f"[{flag}] {r['status']} {r['method']:6} {r['path']}")

    if errors:
        print("\n" + "=" * 78)
        print(f"5xx 明细（{len(errors)} 个）")
        print("=" * 78)
        for r in errors:
            print(f"\n### {r['status']} {r['method']} {r['url']}")
            print(r["body"])

    with open("tests/api/_connectivity_report.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    return 1 if errors else 0


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        token = login(client)
        client.headers["Authorization"] = f"Bearer {token}"
        overrides = discover_ids(client)
        print(f"路径参数覆盖：{overrides}")
        return report(probe_all(client, overrides))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""临时脚本：用用户 API Key 创建站点，并把已存在的规则绑定到该站点。

认证方式
--------
所有请求携带 ``Authorization: Bearer <fy_...>`` 头。admin-api 在
``get_current_user_id`` 中按凭据前缀分流：``fy_`` 前缀走用户 API Key 校验，
其余走 JWT。

涉及接口（请求 / 返回参数）
---------------------------
1. GET /v2/sites                站点列表（分页）
   请求(query，均可选)：appId=int, keyword=str, isActive=bool,
                        accessMode=str, page=int, pageSize=int
   返回：SiteListResponse，直接返回分页体（无 SuccessResponse 包裹）
         { items: [{id, site_key, app_id, app_name, name, domain,
                    alt_domains, access_mode, sdk_version, gateway_url,
                    is_active, clock_stats_enabled, log_retention_days,
                    remark, created_at, updated_at, rule_count, rules}],
           total:int, page:int, page_size:int }

2. POST /v2/sites               创建站点
   请求体：SiteCreateRequest
           { app_id:int(必填), name:str(必填), domain:str(必填),
             alt_domains:list[str], access_mode:str("adapter"/"sdk"),
             sdk_version:str|None, gateway_url:str|None,
             clock_stats_enabled:bool, log_retention_days:int, remark:str|None }
   返回：SiteDetailResponse（继承 SiteResponse，额外含 site_secret，仅创建/轮换时返回）

3. POST /v2/rules/bind-to-site/{site_id}   绑定规则（全量覆盖该站点规则列表）
   路径参数：site_id=int
   请求体：BindRulesRequest { rule_ids: list[int] }
   返回：SuccessResponse[dict]
         data = { bound:int(实际绑定条数), conflicts:dict(冲突检测展示结果) }
"""

import json
import sys
from typing import Any

import httpx

# ══════════════════════════════════════════════════════════════
# 配置区（临时脚本，直接改这里，不读 .env）
# ══════════════════════════════════════════════════════════════
API_KEY = "fy_xxxxxxxx"                # 用户 API Key
BASE_URL = "http://localhost:8081"      # admin-api 地址（不带末尾斜杠）
APP_ID = 1                              # 应用 ID
RULE_IDS = [1, 2, 3]                    # 已存在的规则 ID（只绑定，不创建）

SITE = {
    "name": "示例站点",
    "domain": "example.com",
    "alt_domains": [],
    "access_mode": "sdk",               # adapter / sdk
    "sdk_version": None,
    "gateway_url": None,
    "clock_stats_enabled": True,
    "log_retention_days": 30,
    "remark": "由临时脚本创建",
}

# Windows 控制台默认 GBK，打印中文会抛 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _body(resp: httpx.Response) -> dict[str, Any]:
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def api(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resp = client.request(method, path, json=payload)
    body = _body(resp)
    if resp.is_error:
        raise RuntimeError(
            f"{method} {path} -> HTTP {resp.status_code}: "
            f"{json.dumps(body, ensure_ascii=False)}"
        )
    return body


def list_sites(client: httpx.Client, app_id: int | None = None) -> list[dict[str, Any]]:
    """站点列表（GET /v2/sites 直接返回分页体，无 SuccessResponse 包裹）。"""
    params: dict[str, Any] = {"page": 1, "pageSize": 100}
    if app_id is not None:
        params["appId"] = app_id
    resp = client.request("GET", "/v2/sites", params=params)
    body = _body(resp)
    if resp.is_error:
        raise RuntimeError(
            f"GET /v2/sites -> HTTP {resp.status_code}: "
            f"{json.dumps(body, ensure_ascii=False)}"
        )
    return body.get("items") or []


def main() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        timeout=15.0,
        headers={"Authorization": f"Bearer {API_KEY}"},
    ) as client:
        # 1. 列出当前应用下的站点。
        sites = list_sites(client, app_id=APP_ID)
        print(f"[1/3] 当前应用（app_id={APP_ID}）站点列表，共 {len(sites)} 个：")
        for s in sites:
            print(f"  - id={s['id']} name={s['name']} domain={s['domain']} rules={s.get('rule_count', 0)}")

        # 2. 创建站点（app_id 为必填）。
        site = (api(client, "POST", "/v2/sites", payload={**SITE, "app_id": APP_ID}).get("data") or {})
        site_id = site["id"]
        print(f"[2/3] 站点创建成功：id={site_id} site_key={site.get('site_key')}")

        # 3. 绑定已存在的规则（全量覆盖该站点绑定的规则列表）。
        result = (
            api(
                client,
                "POST",
                f"/v2/rules/bind-to-site/{site_id}",
                payload={"rule_ids": RULE_IDS},
            ).get("data")
            or {}
        )
        print(f"[3/3] 规则绑定完成：bound={result.get('bound')} conflicts={result.get('conflicts')}")

    print(json.dumps({"site_id": site_id, "rule_ids": RULE_IDS}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

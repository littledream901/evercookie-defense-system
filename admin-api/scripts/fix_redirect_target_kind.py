"""一次性修数：把 mechanism=redirect 但 target.kind != url 的处置改回 url。

背景：biz_rule 里存在早于 disposition 契约校验（_MECHANISM_TARGET_KINDS）
写入的行，redirect 配了 target.kind=origin。这类行读出来时 model_validate
必然抛 ValueError，导致规则列表整个 500。

用法（在 admin-api 目录下）：
    python scripts/fix_redirect_target_kind.py
"""

import asyncio
import json
import os
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_ENV = Path(__file__).resolve().parent.parent / ".env"


def _load_db_url() -> str | None:
    """取 ADMIN_DATABASE_URL（admin 的实际库），统一成 async 驱动。"""
    url = os.getenv("ADMIN_DATABASE_URL")
    if not url and _ENV.exists():
        for line in _ENV.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^ADMIN_DATABASE_URL=(.+)$", line.strip())
            if m:
                url = m.group(1).strip()
                break
    if not url:
        return None
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)
    elif url.startswith("mysql+pymysql://"):
        url = url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
    return url


async def fix_redirect_rules():
    """扫描并修复 redirect 规则的 target.kind。"""
    db_url = _load_db_url()
    if not db_url:
        print("ERROR: ADMIN_DATABASE_URL not found")
        return

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, disposition_match, disposition_miss FROM biz_rule WHERE kind = 'decision'")
        )
        rows = result.fetchall()

        fixed_count = 0
        for row_id, disp_match_raw, disp_miss_raw in rows:
            updates = {}

            # 修复 disposition_match
            if disp_match_raw:
                disp_match = json.loads(disp_match_raw) if isinstance(disp_match_raw, str) else disp_match_raw
                if disp_match.get("mechanism") == "redirect":
                    target = disp_match.get("target", {})
                    if target.get("kind") != "url":
                        print(f"[Rule {row_id}] disposition_match: fix target.kind={target.get('kind')} -> url")
                        target["kind"] = "url"
                        disp_match["target"] = target
                        updates["disposition_match"] = json.dumps(disp_match)

            # 修复 disposition_miss
            if disp_miss_raw:
                disp_miss = json.loads(disp_miss_raw) if isinstance(disp_miss_raw, str) else disp_miss_raw
                if disp_miss.get("mechanism") == "redirect":
                    target = disp_miss.get("target", {})
                    if target.get("kind") != "url":
                        print(f"[Rule {row_id}] disposition_miss: fix target.kind={target.get('kind')} -> url")
                        target["kind"] = "url"
                        disp_miss["target"] = target
                        updates["disposition_miss"] = json.dumps(disp_miss)

            # 执行更新
            if updates:
                if "disposition_match" in updates and "disposition_miss" in updates:
                    await conn.execute(
                        text("UPDATE biz_rule SET disposition_match = :match, disposition_miss = :miss WHERE id = :id"),
                        {"match": updates["disposition_match"], "miss": updates["disposition_miss"], "id": row_id}
                    )
                elif "disposition_match" in updates:
                    await conn.execute(
                        text("UPDATE biz_rule SET disposition_match = :match WHERE id = :id"),
                        {"match": updates["disposition_match"], "id": row_id}
                    )
                elif "disposition_miss" in updates:
                    await conn.execute(
                        text("UPDATE biz_rule SET disposition_miss = :miss WHERE id = :id"),
                        {"miss": updates["disposition_miss"], "id": row_id}
                    )
                fixed_count += 1

        if fixed_count > 0:
            print(f"\nOK: Fixed {fixed_count} rules")
        else:
            print("OK: No rules need fixing")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_redirect_rules())

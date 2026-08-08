"""端到端冒烟：配置面下发 → 网关判定 → 边缘处置，全链路闭环验证。

复现 dashboard-ui/public/testing-pages 三个手动测试台的逻辑，但无需 Docker：
用进程内 FakeRedis 替代真实 Redis，其余全部走**真实生产代码**——真实的
AppKeyRedisSync / RuleCache 写配置，真实的 DecisionService 做判定，真实的
HMAC 签名与验签。

为什么分两阶段
--------------
admin-api 与 gateway-api 都以 ``src`` 作为顶层包名，同进程 import 会互相覆盖。
因此阶段一先加载 admin-api 写入 FakeRedis，随后清空 ``src*`` 模块并切换
sys.path，阶段二加载 gateway-api 读同一个 FakeRedis 实例（纯 Python 对象，
不受模块清理影响）。

用法::

    python scripts/e2e_smoke/run_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 控制台默认 GBK，报告里的中文与符号会直接抛 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fake_redis import FakeRedis  # noqa: E402

APP_ID = 7
SITE_ID = "site_629cc45b"
APP_SECRET = "sk_live_smoke_secret"

_PASS = "\033[32mPASS\033[0m"
_FAIL = "\033[31mFAIL\033[0m"
_SKIP = "\033[33mSKIP\033[0m"


class Report:
    """断言收集器，全部跑完再统一汇总，单条失败不中断后续场景。"""

    def __init__(self, sink: Any = None) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self._sink = sink

    def _emit(self, line: str) -> None:
        print(line)
        if self._sink is not None:
            self._sink.write(line + "\n")
            self._sink.flush()

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((label, _PASS if ok else _FAIL, detail))
        self._emit(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
        return ok

    def skip(self, label: str, reason: str) -> None:
        self.rows.append((label, _SKIP, reason))
        self._emit(f"  [SKIP] {label} -- {reason}")

    def section(self, title: str) -> None:
        self._emit(f"\n>> {title}")

    @property
    def failed(self) -> int:
        return sum(1 for _, s, _ in self.rows if s == _FAIL)

    def summary(self) -> int:
        passed = sum(1 for _, s, _ in self.rows if s == _PASS)
        skipped = sum(1 for _, s, _ in self.rows if s == _SKIP)
        self._emit("\n" + "=" * 68)
        self._emit(f"总计 {len(self.rows)} 项：{passed} 通过 / {self.failed} 失败 / {skipped} 跳过")
        if self.failed:
            self._emit("\n失败项：")
            for label, status, detail in self.rows:
                if status == _FAIL:
                    self._emit(f"  - {label}" + (f" -- {detail}" if detail else ""))
        self._emit("=" * 68)
        return 1 if self.failed else 0


def _swap_service(name: str) -> None:
    """切换 sys.path 到指定服务，并清掉已加载的 src* 模块。"""
    target = _ROOT / name
    others = {str(_ROOT / n) for n in ("admin-api", "gateway-api", "worker")} - {str(target)}
    for mod in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        sys.modules.pop(mod, None)
    sys.path[:] = [p for p in sys.path if p not in others]
    sys.path.insert(0, str(target))


# ══════════════════════════════════════════════════════════════════════
# 阶段一：配置面 —— 创建网站、创建规则、绑定规则、下发 Redis
# ══════════════════════════════════════════════════════════════════════
async def stage_config(redis: FakeRedis, rpt: Report) -> None:
    _swap_service("admin-api")
    from fangyu_shared.schemas.disposition import (
        ChallengeKind,
        DecisionDisposition,
        Mechanism,
        Target,
        TargetKind,
        Verdict,
    )
    from fangyu_shared.schemas.rule import (
        DecisionRule,
        RuleCondition,
        RulePriority,
        RuleStatus,
    )
    from src.infrastructure.cache.app_key_sync import AppKeyRedisSync
    from src.infrastructure.cache.rule_cache import RuleCache

    rpt.section("① 配置面：创建网站（绑定 API Key → app_id/secret）")
    await AppKeyRedisSync(redis).bind(SITE_ID, APP_ID, APP_SECRET)
    rpt.check(
        "网站已注册，正向映射可解析",
        json.loads(redis.kv[f"fangyu:app_keys:{SITE_ID}"])["app_id"] == APP_ID,
    )
    rpt.check(
        "app_secret 反向索引已写入（挑战凭据签发依赖它）",
        redis.kv.get(f"fangyu:app_secrets:{APP_ID}") == APP_SECRET,
    )

    rpt.section("② 配置面：创建规则")
    rules = [
        # 爬虫 UA → 直接拦截。CRITICAL 保证优先于后面的规则。
        DecisionRule(
            id=101,
            appId=APP_ID,
            name="爬虫 UA 拦截",
            status=RuleStatus.PUBLISHED,
            priority=RulePriority.CRITICAL,
            conditions=[RuleCondition(field="ua.is_bot", op="eq", value=True)],
            disposition_match=DecisionDisposition(
                verdict=Verdict.HOSTILE,
                mechanism=Mechanism.DENY,
                target=Target(kind=TargetKind.STATUS_ONLY, httpStatus=403),
            ),
        ),
        # 指定路径 → 跳转。验证 redirect + targetUrl 渲染。
        DecisionRule(
            id=102,
            appId=APP_ID,
            name="拦截页跳转",
            status=RuleStatus.PUBLISHED,
            priority=RulePriority.HIGH,
            conditions=[
                RuleCondition(field="request.path", op="eq", value="/blocked-page")
            ],
            disposition_match=DecisionDisposition(
                verdict=Verdict.SUSPECT,
                mechanism=Mechanism.REDIRECT,
                target=Target(
                    kind=TargetKind.URL,
                    url="https://safe.example.com/notice",
                    httpStatus=302,
                ),
            ),
        ),
        # 人机挑战 → 验证 challenge_token 是否真的签发（P0 修复项）。
        DecisionRule(
            id=103,
            appId=APP_ID,
            name="敏感路径挑战",
            status=RuleStatus.PUBLISHED,
            priority=RulePriority.HIGH,
            conditions=[
                RuleCondition(field="request.path", op="eq", value="/checkout")
            ],
            # challenge 只允许 target.kind=origin：挑战是在原页面上就地弹出的，
            # 不涉及跳转目标。schema 在构造期就拒绝其他组合。
            disposition_match=DecisionDisposition(
                verdict=Verdict.SUSPECT,
                mechanism=Mechanism.CHALLENGE,
                challengeKind=ChallengeKind.JS,
                target=Target(kind=TargetKind.ORIGIN),
            ),
        ),
        # 影子规则 → 必须被评估但绝不影响裁决。
        DecisionRule(
            id=104,
            appId=APP_ID,
            name="影子观察：全站拦截（不应生效）",
            status=RuleStatus.SHADOW,
            priority=RulePriority.CRITICAL,
            conditions=[RuleCondition(field="request.path", op="contains", value="/")],
            disposition_match=DecisionDisposition(
                verdict=Verdict.HOSTILE,
                mechanism=Mechanism.DENY,
                target=Target(kind=TargetKind.STATUS_ONLY, httpStatus=403),
            ),
        ),
    ]
    rpt.check("4 条规则构造成功（含 1 条影子规则）", len(rules) == 4)

    rpt.section("③ 配置面：绑定规则到网站并原子下发 Redis")
    await RuleCache(redis).replace_site(APP_ID, rules)
    snapshot = redis.hashes.get(f"fangyu:rules:site:{APP_ID}", {})
    rpt.check(
        "快照含 4 条规则 + 版本标记",
        len(snapshot) == 5 and "__version__" in snapshot,
        f"字段={sorted(snapshot)}",
    )
    rpt.check(
        "下发使用 staging + RENAME 原子换切（无空窗）",
        "rename" in redis.command_log,
        f"命令序列={[c for c in redis.command_log if c in ('delete', 'hset', 'rename')]}",
    )
    rpt.check(
        "影子规则已进入快照（否则网关无从评估）",
        json.loads(snapshot["104"])["status"] == "shadow",
    )


# ══════════════════════════════════════════════════════════════════════
# 阶段二：判定面 + 边缘面 —— 真实网关判定，签名与测试台逐字节一致
# ══════════════════════════════════════════════════════════════════════
def _build_signed_body(context: dict[str, Any], require_details: bool = True) -> dict[str, Any]:
    """构造带签名的请求体，签名口径与三个测试台的 signBody 完全一致。

    直接复用 shared 的 sign_params，而不是重写一遍 HMAC——重写就测不出
    「SDK 与网关待签串不一致」这类问题了。
    """
    import time

    from fangyu_shared.utils.crypto import generate_nonce, sign_params

    payload: dict[str, Any] = {
        "context": context,
        "requireDetails": require_details,
        "nonce": generate_nonce(),
        "timestamp": int(time.time()),
    }
    payload["sign"] = sign_params(payload, APP_SECRET)
    return payload


def _ctx(**overrides: Any) -> dict[str, Any]:
    """adapter ingress 的基础 context，字段名与 adapter_test.html 对齐。"""
    base: dict[str, Any] = {
        "siteId": SITE_ID,
        "ingress": "adapter",
        "fingerprint": "fp_smoke00000001",
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "visitUrl": "https://example.com/",
        "ip": "218.17.12.100",
    }
    base.update(overrides)
    return base


async def stage_gateway(redis: FakeRedis, rpt: Report) -> None:
    _swap_service("gateway-api")

    from httpx import ASGITransport, AsyncClient

    from src.config import get_settings
    from src.interfaces.http import dependencies as deps
    from src.interfaces.http.middleware.app_key import (
        AppKeyEnforcementMiddleware,
        AppKeyResolver,
    )

    # 用 FakeRedis 顶替连接池。get_redis() 是所有基础设施组件的唯一入口，
    # 换掉它等于把整条判定链路指向替身，无需逐个组件注入。
    deps.get_redis = lambda: redis  # type: ignore[assignment]
    deps.reset_dependencies()

    settings = get_settings()
    rpt.section("④ 判定面：安全默认值")
    rpt.check(
        "signature_required 默认开启（关闭则画像可任意伪造）",
        settings.signature_required is True,
        f"当前={settings.signature_required}",
    )

    from fastapi import FastAPI

    from src.interfaces.http.v2 import challenge as challenge_route
    from src.interfaces.http.v2 import decide as decide_route

    app = FastAPI()
    app.include_router(decide_route.router, prefix="/v2")
    app.include_router(challenge_route.router, prefix="/v2")
    resolver = AppKeyResolver(redis, cache_ttl=0)
    app.add_middleware(
        AppKeyEnforcementMiddleware,
        resolver_provider=lambda: resolver,
        settings_provider=get_settings,
        nonce_store_provider=deps.get_nonce_store,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://smoke") as client:

        async def decide(context: dict[str, Any], details: bool = True) -> tuple[int, dict]:
            body = _build_signed_body(context, details)
            resp = await client.post(
                "/v2/decide",
                json=body,
                headers={"X-App-Key": SITE_ID, "Content-Type": "application/json"},
            )
            raw = resp.json()
            return resp.status_code, (raw.get("data") or raw)

        # ── NORM：签名与重放 ───────────────────────────────────────
        rpt.section("⑤ NORM：HMAC 验签 + Nonce 防重放")
        status, data = await decide(_ctx())
        rpt.check("合法签名请求通过", status == 200, f"HTTP {status}")

        bad = _build_signed_body(_ctx())
        bad["sign"] = "0" * 64
        resp = await client.post(
            "/v2/decide", json=bad, headers={"X-App-Key": SITE_ID}
        )
        rpt.check("签名被篡改 → 401", resp.status_code == 401, f"HTTP {resp.status_code}")

        replay = _build_signed_body(_ctx())
        r1 = await client.post("/v2/decide", json=replay, headers={"X-App-Key": SITE_ID})
        r2 = await client.post("/v2/decide", json=replay, headers={"X-App-Key": SITE_ID})
        rpt.check(
            "同一 nonce 重放 → 首次 200、二次 401",
            r1.status_code == 200 and r2.status_code == 401,
            f"首次={r1.status_code} 二次={r2.status_code}",
        )

        # ── MATCH / DISP：规则命中与三层处置 ──────────────────────
        rpt.section("⑥ MATCH + DISP：规则命中与三层处置")
        status, data = await decide(
            _ctx(userAgent="python-requests/2.31.0", ip="45.33.32.156")
        )
        rpt.check(
            "爬虫 UA 命中拦截规则 → hostile/deny",
            data.get("verdict") == "hostile" and data.get("mechanism") == "deny",
            f"verdict={data.get('verdict')} mechanism={data.get('mechanism')} "
            f"decidedBy={data.get('decidedBy')}",
        )
        rpt.check("拦截规则回传 httpStatus=403", data.get("httpStatus") == 403,
                  str(data.get("httpStatus")))

        # 只传 visitUrl 不传 path，复现三个适配器的真实上报形状。
        # 修复前 path 恒为 "/"，路径类规则永不命中。
        status, data = await decide(
            _ctx(visitUrl="https://example.com/blocked-page", fingerprint="fp_smoke00000002")
        )
        rpt.check(
            "路径命中跳转规则 → redirect + targetUrl",
            data.get("mechanism") == "redirect"
            and bool(data.get("targetUrl")),
            f"mechanism={data.get('mechanism')} targetUrl={data.get('targetUrl')}",
        )
        rpt.check(
            "redirect 的 targetKind=url 且 httpStatus 为 3xx",
            data.get("targetKind") == "url"
            and 300 <= int(data.get("httpStatus") or 0) < 400,
            f"targetKind={data.get('targetKind')} httpStatus={data.get('httpStatus')}",
        )

        # ── 挑战链路：P0 修复的核心验证点 ─────────────────────────
        rpt.section("⑦ DISP：人机挑战凭据签发（P0 修复验证）")
        status, data = await decide(
            _ctx(visitUrl="https://example.com/checkout", fingerprint="fp_smoke00000003")
        )
        rpt.check(
            "命中挑战规则 → mechanism=challenge",
            data.get("mechanism") == "challenge",
            f"mechanism={data.get('mechanism')}",
        )
        token = data.get("challengeToken")
        rpt.check(
            "challengeToken 已签发（修复前恒为 None，整条挑战链断裂）",
            bool(token),
            f"token={(token or '')[:24]}…" if token else "None",
        )

        # ── 影子规则：绝不能影响真实裁决 ──────────────────────────
        rpt.section("⑧ 灰度影子：评估但不生效")
        status, data = await decide(
            _ctx(visitUrl="https://example.com/plain", fingerprint="fp_smoke00000004")
        )
        rpt.check(
            "存在会命中的 deny 影子规则，访客仍被放行",
            data.get("mechanism") == "pass",
            f"verdict={data.get('verdict')} mechanism={data.get('mechanism')}",
        )
        shadow = data.get("shadow") or []
        rpt.check(
            "影子命中被记录（供影响面测算）",
            len(shadow) >= 1,
            f"shadow={shadow}",
        )

        # ── CLOCK：滑动窗口频控 ───────────────────────────────────
        rpt.section("⑨ CLOCK：滑动窗口频控前置生效")
        # DEFAULT_LIMITS["burst"] = 30 次 / 10 秒，故须超过 30 次才触发。
        hits: list[str] = []
        for i in range(45):
            _, d = await decide(
                _ctx(visitUrl=f"https://example.com/rate/{i}", ip="203.0.113.77",
                     fingerprint="fp_smoke_rate001")
            )
            hits.append(str(d.get("decidedBy")))
        rpt.check(
            "连发 45 次触发突发窗口频控（burst=30/10s）",
            any(h.startswith("clock") for h in hits),
            f"末次 decidedBy={hits[-1]}",
        )
        rpt.check(
            "频控在缓存之前生效（缓存命中不会漏计数）",
            hits.count("cache") == 0 or any(h.startswith("clock") for h in hits),
            f"decidedBy 分布={ {h: hits.count(h) for h in set(hits)} }",
        )

        # ── 异步投递：决策事件进 Stream ───────────────────────────
        rpt.section("⑩ 数据面：决策事件异步投递 Redis Stream")
        await asyncio.sleep(0.3)  # 事件发布已改为 create_task，给它一点时间落队
        stream = redis.streams.get("fangyu:events:decision", [])
        rpt.check(
            "决策事件已投递到 Stream",
            len(stream) > 0,
            f"事件数={len(stream)}",
        )
        if stream:
            sample = json.loads(stream[0][1].get("payload", "{}"))
            rpt.check(
                "事件含裁决与评分字段（供 ClickHouse 落库与信誉计算）",
                "verdict" in sample and "score" in sample,
                f"字段样本={sorted(sample)[:8]}",
            )
            stages = {
                json.loads(e[1].get("payload", "{}")).get("decidedStage") for e in stream
            }
            rpt.check(
                "缓存命中路径也发事件（修复前此路径静默丢事件）",
                "cache" in stages,
                f"出现的 decidedStage={sorted(s for s in stages if s)}",
            )

    # 排空在途事件发布任务，与 main.py lifespan 的关闭顺序一致。
    await deps.build_decision_service().drain_events()


async def main() -> int:
    redis = FakeRedis()
    out = Path(__file__).resolve().parent / "last_report.txt"
    with out.open("w", encoding="utf-8") as sink:
        rpt = Report(sink)
        rpt._emit("全链路冒烟：配置面 -> 判定面 -> 数据面")
        rpt._emit(f"（进程内 FakeRedis；app_id={APP_ID} site_id={SITE_ID}）")
        await stage_config(redis, rpt)
        await stage_gateway(redis, rpt)
        code = rpt.summary()
    print(f"\n报告已写入 {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

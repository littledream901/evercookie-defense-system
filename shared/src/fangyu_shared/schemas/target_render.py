"""处置目标 URL 渲染。

为什么单独成模块
----------------
决策缓存按 (app_id, fingerprint, ip) 命中，**不含 URL**。若在写缓存前就把
``{path}``/``{url}`` 渲染成具体地址，同一访客访问不同页面时会复用第一次的
渲染结果，跳转地址串味。因此渲染必须发生在缓存**之后**、构造响应时。

安全约束
--------
渲染结果的协议限制在 http/https。占位符值来自请求，攻击者可通过构造
``visit_url`` 影响输出，若不校验可产出 ``javascript:`` 等协议造成 XSS。
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from urllib.parse import quote as urlquote
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https", ""})
"""空串表示相对路径（如 /safe.html），允许。"""


def clean_url(url: str | None) -> str | None:
    """清理 URL：去空白与误粘的反引号。"""
    if not isinstance(url, str):
        return None
    cleaned = url.strip().strip("`").strip()
    return cleaned or None


def render_target(
    url: str | None,
    *,
    visit_url: str = "",
    app_id: int | str = "",
    request_id: str = "",
    # 访客画像变量
    ip: str = "",
    fingerprint: str = "",
    country: str = "",
    verdict: str = "",
    score: float | str = "",
    connection_type: str = "",
    is_vpn: bool = False,
    is_proxy: bool = False,
    # 请求信号变量
    user_agent: str = "",
    referer: str = "",
    ingress: str = "",
) -> str | None:
    """渲染目标 URL 占位符。

    请求维度
    --------
    ``{scheme}`` ``{host}`` ``{path}`` ``{query}`` ``{url}``
    ``{url_enc}``（URL 编码的完整地址，适合做 redirect back 参数）
    ``{app_id}`` ``{request_id}`` ``{ts}``（Unix 秒级时间戳）

    访客画像维度
    ------------
    ``{ip}`` ``{ip_enc}`` ``{fingerprint}`` ``{fingerprint_enc}``
    ``{country}``（ISO-3166 国家码，如 CN / US）
    ``{verdict}``（hostile / suspicious / clean / unknown）
    ``{score}``（浮点字符串，如 82.5）``{score_int}``（整数字符串，如 82）
    ``{connection_type}``（datacenter / mobile / residential / education / government）
    ``{is_vpn}`` ``{is_proxy}``（1 / 0）

    请求信号维度
    ------------
    ``{ua_enc}``（URL 编码的 User-Agent）
    ``{referer_enc}``（URL 编码的 Referer）
    ``{ingress}``（sdk / adapter）

    安全约束
    --------
    协议不在白名单内时返回 ``None``，调用方应降级为不跳转，防止
    ``javascript:`` 等危险协议被注入。
    占位符值来自请求，其中 visit_url / referer / ua 由攻击者可控，
    因此使用 ``urlquote`` 对这些值做 URL 编码再插入，避免二次注入。
    """
    cleaned = clean_url(url)
    if not cleaned:
        return None

    parsed = urlparse(visit_url or "")
    path = parsed.path or "/"
    # SPA hash 路由：#/foo?a=1 时真实路径在 fragment 里
    if path == "/" and parsed.fragment.startswith("/"):
        path = parsed.fragment.split("?", 1)[0] or "/"

    score_str = str(score) if score != "" else ""
    try:
        score_int_str = str(int(float(score))) if score != "" else ""
    except (ValueError, TypeError):
        score_int_str = ""

    replacements = {
        # 请求维度
        "{scheme}":        parsed.scheme,
        "{host}":          parsed.netloc,
        "{path}":          path,
        "{query}":         f"?{parsed.query}" if parsed.query else "",
        "{url}":           visit_url or "",
        "{url_enc}":       urlquote(visit_url or "", safe=""),
        "{app_id}":        str(app_id or ""),
        "{request_id}":    request_id or "",
        "{ts}":            str(int(time.time())),
        # 访客画像
        "{ip}":            ip or "",
        "{ip_enc}":        urlquote(ip or "", safe=""),
        "{fingerprint}":   fingerprint or "",
        "{fingerprint_enc}": urlquote(fingerprint or "", safe=""),
        "{country}":       country or "",
        "{verdict}":       verdict or "",
        "{score}":         score_str,
        "{score_int}":     score_int_str,
        "{connection_type}": connection_type or "",
        "{is_vpn}":        "1" if is_vpn else "0",
        "{is_proxy}":      "1" if is_proxy else "0",
        # 请求信号
        "{ua_enc}":        urlquote(user_agent or "", safe=""),
        "{referer_enc}":   urlquote(referer or "", safe=""),
        "{ingress}":       ingress or "",
    }
    rendered = cleaned
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)

    rendered = clean_url(rendered)
    if not rendered:
        return None
    if urlparse(rendered).scheme.lower() not in _ALLOWED_SCHEMES:
        return None
    return rendered


def pick_target(pool: Sequence[str], *, seed: str) -> str | None:
    """从地址池按 ``seed`` 稳定取模选一个（旧版 JUMP_MODE=2 的轮询）。

    为什么不用内置 ``hash()``
    ------------------------
    CPython 对 str 的 ``hash()`` 带进程级随机盐（PYTHONHASHSEED），多副本
    网关会对同一个 seed 得出不同下标。这不会报错，只会让「同一请求在不同
    副本上跳到不同地址」变成偶发现象——是排障成本最高的那类 bug。
    ``blake2b`` 跨进程、跨版本、跨平台恒定。

    为什么按请求而非按访客
    --------------------
    轮询的目的是分摊落地页压力与风险；若用 fingerprint 做 seed，同一访客
    永远落在同一个地址，池子退化成「按访客分片」，起不到分摊作用。
    """
    candidates = [u for u in pool if isinstance(u, str) and u.strip()]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return candidates[int.from_bytes(digest, "big") % len(candidates)]


def _stable_index(seed: str, modulo: int) -> int:
    """blake2b 稳定取模。不用内置 hash()——见 pick_target 的说明。"""
    if modulo <= 0:
        return 0
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % modulo


def pick_weighted(entries: Sequence[tuple[str, int]], *, seed: str) -> str | None:
    """按权重选址。``entries`` 是 (url, weight) 序列。

    无状态实现：把权重摊成一条数轴，用 blake2b 落点。权重 3:1 时 A 占
    数轴前 3/4，落点命中概率即为 75%——不需要计数器就能得到稳定比例。
    """
    usable = [(u, w) for u, w in entries if isinstance(u, str) and u.strip() and w > 0]
    if not usable:
        return None
    if len(usable) == 1:
        return usable[0][0]
    total = sum(w for _, w in usable)
    point = _stable_index(seed, total)
    cursor = 0
    for url, weight in usable:
        cursor += weight
        if point < cursor:
            return url
    return usable[-1][0]


def pick_by_index(pool: Sequence[str], index: int) -> str | None:
    """按外部给定的下标取址（ROUND_ROBIN 用，下标来自 Redis 计数器）。

    取模在此完成而非调用方：计数器是单调递增的，调用方不该关心池子长度。
    """
    candidates = [u for u in pool if isinstance(u, str) and u.strip()]
    if not candidates:
        return None
    return candidates[index % len(candidates)]


def resolve_rotation_order(
    entries: Sequence[tuple[str, int, bool]],
    *,
    strategy: str,
    request_seed: str,
    visitor_seed: str = "",
    counter: int | None = None,
    healthy: Callable[[str], bool] | None = None,
    exhausted: Callable[[str], bool] | None = None,
) -> list[str]:
    """按轮询策略解析候选地址的**优先顺序**。

    返回顺序而非单个地址：渲染可能失败（协议非法、占位符渲染成空），调用
    方需要顺延到下一个。把「选谁」和「渲染失败怎么办」分开，策略只负责排序。

    参数
    ----
    entries
        (url, weight, enabled) 三元组序列。
    strategy
        ``RotationStrategy`` 的值。未知策略退化为 hash——新增策略时旧网关
        不会因为不认识而整条规则失效。
    request_seed
        按请求分摊用的种子（通常是 request_id）。
    visitor_seed
        按访客固定用的种子（通常是 fingerprint），仅 sticky 使用。
    counter
        Redis 单调计数器，仅 round_robin 使用。为 None 时退化为 hash。
    healthy
        健康判定回调。返回 False 的地址会被排到末尾而非直接剔除——全池
        不健康时仍要给出候选，否则整条规则静默失效。
    exhausted
        配额耗尽判定回调。返回 True 的地址会被排到末尾。与 healthy 同理，
        全池打满时仍给出候选作为兜底，避免整条规则静默失效。
    """
    usable = [
        (u, w, en)
        for u, w, en in entries
        if isinstance(u, str) and u.strip() and en and w > 0
    ]
    if not usable:
        return []

    urls = [u for u, _, _ in usable]

    if strategy == "weighted":
        first = pick_weighted([(u, w) for u, w, _ in usable], seed=request_seed)
    elif strategy == "sticky":
        # 按访客固定：牺牲分摊性换会话连续性
        first = pick_target(urls, seed=visitor_seed or request_seed)
    elif strategy == "round_robin":
        first = pick_by_index(urls, counter) if counter is not None else pick_target(urls, seed=request_seed)
    elif strategy == "failover":
        # 主备：按配置顺序，第一个健康的优先
        first = next((u for u in urls if healthy is None or healthy(u)), urls[0])
    else:
        # hash 及未知策略
        first = pick_target(urls, seed=request_seed)

    ordered = [first, *[u for u in urls if u != first]] if first else urls

    # 不健康的排到末尾（而非剔除）：全池不健康时仍需给出候选
    if healthy is not None:
        ordered.sort(key=lambda u: 0 if healthy(u) else 1)

    # 配额打满的排到末尾：全池打满时仍需给出候选
    if exhausted is not None:
        ordered.sort(key=lambda u: 0 if not exhausted(u) else 1)

    return ordered


def render_pool(
    pool: Sequence[str],
    *,
    seed: str,
    visit_url: str = "",
    app_id: int | str = "",
    request_id: str = "",
    # 访客画像变量（透传给 render_target）
    ip: str = "",
    fingerprint: str = "",
    country: str = "",
    verdict: str = "",
    score: float | str = "",
    connection_type: str = "",
    is_vpn: bool = False,
    is_proxy: bool = False,
    user_agent: str = "",
    referer: str = "",
    ingress: str = "",
) -> str | None:
    """轮询选址 + 渲染占位符，并在渲染失败时顺延到池内其他地址。

    顺延而非直接失败：地址池的存在本身就是为了容错，若选中的那条恰好配错
    （协议非法、占位符渲染成空），把整个处置降级为放行等于让一条错配的
    备用地址废掉整条规则。
    """
    candidates = [u for u in pool if isinstance(u, str) and u.strip()]
    if not candidates:
        return None
    first = pick_target(candidates, seed=seed)
    ordered = [first, *[u for u in candidates if u != first]] if first else candidates
    for candidate in ordered:
        if candidate is None:
            continue
        rendered = render_target(
            candidate,
            visit_url=visit_url,
            app_id=app_id,
            request_id=request_id,
            ip=ip,
            fingerprint=fingerprint,
            country=country,
            verdict=verdict,
            score=score,
            connection_type=connection_type,
            is_vpn=is_vpn,
            is_proxy=is_proxy,
            user_agent=user_agent,
            referer=referer,
            ingress=ingress,
        )
        if rendered:
            return rendered
    return None

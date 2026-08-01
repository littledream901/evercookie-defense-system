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
) -> str | None:
    """渲染目标 URL 占位符。

    支持 ``{scheme}`` ``{host}`` ``{path}`` ``{query}`` ``{url}``
    ``{app_id}`` ``{request_id}``。

    协议不在白名单内时返回 ``None``，调用方应降级为不跳转。
    """
    cleaned = clean_url(url)
    if not cleaned:
        return None

    parsed = urlparse(visit_url or "")
    path = parsed.path or "/"
    # SPA hash 路由：#/foo?a=1 时真实路径在 fragment 里
    if path == "/" and parsed.fragment.startswith("/"):
        path = parsed.fragment.split("?", 1)[0] or "/"

    replacements = {
        "{scheme}": parsed.scheme,
        "{host}": parsed.netloc,
        "{path}": path,
        "{query}": f"?{parsed.query}" if parsed.query else "",
        "{url}": visit_url or "",
        "{app_id}": str(app_id or ""),
        "{request_id}": request_id or "",
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

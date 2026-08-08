"""App Key 校验与解析。

Gateway 通过 HTTP header 中的 API Key 反查 Redis 得到 site_id：
- 主凭据 header：``X-App-Key``
- 兜底：``Authorization: Bearer <key>``

Redis 键位：``fangyu:app_keys:{site_key}`` → ``{"app_id": <site_id>, "app_secret": "..."}``
注意：Redis 中的 app_id 字段实际存储的是站点主键（Site.id），这是
兼容旧格式 ``str(site_id)``（此时无密钥，无法验签）。

由 admin-api 负责在站点创建 / 轮换 Key / 删除站点时维护映射。
Gateway 侧只读，并配合本地进程内缓存降低 Redis 压力。

安全设计：
- 关键决策端点（/v2/decide*）通过 :class:`AppKeyEnforcementMiddleware` 在 body 解析
  之前完成 API Key 校验，未通过直接返回 401，避免 pydantic 校验先触发 422。
- 校验成功后把 ``ResolvedAppKey`` 写入 ``request.state.resolved_app_key``，
  路由层用 :func:`require_app_key` 依赖再取用。

为什么 API Key 之外还要验签
---------------------------
API Key 走 header 明文传输，且适配器把它写在 Nginx 配置、WordPress 选项表、
CDN 环境变量里，泄露面很大。仅凭 Key 鉴权意味着任何拿到 Key 的人都能伪造
任意访客画像——把自己的 IP 报成干净机房、把爬虫 UA 报成 Chrome，直接骗过
风控。因此对**画像可信度**的保护落在签名上：

1. ``timestamp`` 落在 ±300s 窗口内（双向容忍客户端时钟偏差）；
2. ``nonce`` 在 Redis 中一次性兑付，挡住窗口内的原样重放；
3. ``sign`` = HMAC-SHA256(待签串, app_secret)，待签串由
   :func:`fangyu_shared.utils.crypto.build_sign_payload` 统一构造。

三项校验失败一律返回同一个 401 文案，不区分「Key 错」「签名错」「重放」，
避免把哪一步失败告诉探测方。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import orjson
from fastapi import Request
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from fangyu_shared.exceptions import AuthenticationException
from fangyu_shared.logging import get_logger
from fangyu_shared.utils.crypto import (
    DEFAULT_TIMESTAMP_WINDOW,
    is_timestamp_fresh,
    verify_params_signature,
)

_logger = get_logger("gateway.app_key")


@dataclass(slots=True)
class AppCredential:
    """Redis 中一条 site_key 映射的完整内容。"""

    site_id: int
    """站点主键（Site.id）"""
    site_secret: str | None = None


@dataclass(slots=True)
class ResolvedAppKey:
    """API Key 校验成功后的解析结果。
    
    Note:
        site_id 字段实际存储的是站点主键（Site.id），而非应用主键（Application.id）。
        Redis 键 fangyu:app_keys:{site_key} 中存储的 app_id 字段也是站点主键。
        这是
    """

    site_id: int
    """站点主键（Site.id），用于租户隔离和规则加载。注意：不是应用主键（Application.id）"""
    api_key: str
    signature_verified: bool = False


class AppKeyResolver:
    """API Key → site_id 解析器，带本地 TTL 缓存。"""

    def __init__(
        self,
        redis: Redis,
        *,
        key_prefix: str = "fangyu:app_keys:",
        secret_prefix: str = "fangyu:app_secrets:",
        cache_ttl: int = 60,
        max_cache_size: int = 4096,
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix
        self._secret_prefix = secret_prefix
        self._cache_ttl = max(cache_ttl, 0)
        self._max_cache_size = max_cache_size
        self._cache: dict[str, tuple[AppCredential, float]] = {}

    async def resolve_credential(self, api_key: str) -> AppCredential | None:
        """把 api_key 反查成 :class:`AppCredential`。未命中返回 None。"""
        if not api_key:
            return None

        cached = self._cache_get(api_key)
        if cached is not None:
            return cached

        raw: Any = await self._redis.get(self._prefix + api_key)
        if raw is None:
            return None

        credential = self._parse(api_key, raw)
        if credential is None:
            return None

        self._cache_set(api_key, credential)
        return credential

    async def resolve(self, api_key: str) -> int | None:
        """兼容旧签名：只要 site_id。"""
        credential = await self.resolve_credential(api_key)
        return credential.site_id if credential else None

    async def get_secret_by_site_id(self, site_id: int) -> str | None:
        """反向查询：从 site_id 拿 site_secret，用于 challenge token 签发与校验。

        两级查找：
        1. 本地凭据缓存（热路径，decide 刚鉴权过时命中）
        2. Redis 反向索引 ``fangyu:app_secrets:{site_id}``，由 admin 侧 bind 时写入

        必须有第 2 级：正向键以 api_key 作后缀无法按 site_id 检索，只扫本地缓存时
        多进程部署下处理 /challenge/verify 的进程往往不是处理 /decide 的那个，
        缓存必然未命中，挑战校验会静默失败。

        fail-open：Redis 异常返回 None，由外层降级（签发失败不阻断决策）。
        """
        now = time.monotonic()
        for _api_key, (credential, expire_at) in self._cache.items():
            if expire_at > now and credential.site_id == site_id and credential.site_secret:
                return credential.site_secret

        if site_id <= 0:
            return None
        try:
            raw: Any = await self._redis.get(f"{self._secret_prefix}{site_id}")
        except Exception as exc:  # noqa: BLE001 - Redis 抖动不应让挑战链路抛错
            _logger.warning("site_secret_index_lookup_failed", site_id=site_id, error=str(exc))
            return None
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        secret = str(raw).strip()
        return secret or None

    def _parse(self, api_key: str, raw: Any) -> AppCredential | None:
        """解析 Redis 值，兼容 JSON 与旧的纯数字格式。"""
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        text = str(raw).strip()

        site_id_raw: Any = text
        secret: str | None = None
        if text.startswith("{"):
            try:
                payload = orjson.loads(text)
            except orjson.JSONDecodeError:
                _logger.warning("app_key_mapping_invalid", api_key_prefix=api_key[:6])
                return None
            if not isinstance(payload, dict):
                return None
            site_id_raw = payload.get("site_id") or payload.get("app_id")  # 兼容旧键名
            if not site_id_raw:
                return None

            secret = payload.get("site_secret") or payload.get("app_secret")  # 兼容旧键名
            try:
                site_id = int(site_id_raw)
            except (ValueError, TypeError):
                return None
        else:
            try:
                site_id = int(site_id_raw)
            except (TypeError, ValueError):
                _logger.warning("app_key_mapping_invalid", api_key_prefix=api_key[:6], value=text)
                return None

        if site_id <= 0:
            return None
        return AppCredential(site_id=site_id, site_secret=secret)

    def invalidate(self, api_key: str) -> None:
        """在测试或 admin 侧回调时可主动清缓存。"""
        self._cache.pop(api_key, None)

    def clear(self) -> None:
        self._cache.clear()

    def _cache_get(self, key: str) -> AppCredential | None:
        if self._cache_ttl <= 0:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        if expire_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: AppCredential) -> None:
        if self._cache_ttl <= 0:
            return
        if len(self._cache) >= self._max_cache_size:
            self._cache.pop(next(iter(self._cache)), None)
        self._cache[key] = (value, time.monotonic() + self._cache_ttl)


def extract_api_key(request: Request, *, header_name: str = "X-App-Key") -> str | None:
    """按优先级从请求中提取 API Key。"""
    key = request.headers.get(header_name)
    if key:
        return key.strip()
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


@dataclass(slots=True)
class SignatureCheck:
    """验签结果。``ok=False`` 时 ``reason`` 用于日志，不回给调用方。"""

    ok: bool
    reason: str = ""


async def verify_request_signature(
    request: Request,
    credential: AppCredential,
    *,
    nonce_store: Any | None = None,
    window: int = DEFAULT_TIMESTAMP_WINDOW,
) -> SignatureCheck:
    """校验请求签名：时间戳窗口 → nonce 一次性 → HMAC。

    参数取自 JSON body（适配器统一用 POST + JSON）。GET 请求回退到 query。
    """
    if not credential.site_secret:
        return SignatureCheck(False, "no_site_secret")

    params = await _signable_params(request)
    if params is None:
        return SignatureCheck(False, "unparsable_body")

    sign = str(params.get("sign") or "")
    if not sign:
        return SignatureCheck(False, "missing_sign")

    if not is_timestamp_fresh(params.get("timestamp"), window=window):
        return SignatureCheck(False, "stale_timestamp")

    if not verify_params_signature(params, credential.site_secret, sign):
        return SignatureCheck(False, "bad_signature")

    # 验签通过后才占用 nonce：否则伪造请求能把合法访客的 nonce 提前烧掉。
    nonce = str(params.get("nonce") or "")
    if nonce_store is not None:
        if not nonce:
            return SignatureCheck(False, "missing_nonce")
        if not await nonce_store.claim(credential.site_id, nonce):
            return SignatureCheck(False, "replayed_nonce")

    return SignatureCheck(True)


async def _signable_params(request: Request) -> dict[str, Any] | None:
    """取出参与签名的顶层参数。"""
    if request.method in ("GET", "HEAD"):
        return dict(request.query_params)
    try:
        body = await request.body()
    except Exception:  # pragma: no cover - 客户端断连
        return None
    if not body:
        return {}
    try:
        payload = orjson.loads(body)
    except orjson.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class AppKeyEnforcementMiddleware(BaseHTTPMiddleware):
    """在到达路由 body 解析之前拦截，完成 API Key 校验。

    - 只对配置的 ``protected_patterns`` 生效，默认覆盖 ``/v2/decide*``、
      ``/v2/rule/test`` 与 ``/v2/sdk/*``。``rule/test`` 会回显规则命中逻辑，
      若不鉴权等于把规则边界开放给外部试探；``sdk/*`` 会按 appId 往站点
      时序库写行为事件，不鉴权则任意调用方都能污染他人数据。二者都与决策
      接口同级保护。
    - 未通过校验直接返回 401，格式与 shared 异常处理器保持一致。
    - 通过后把 :class:`ResolvedAppKey` 写入 ``request.state.resolved_app_key``。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        resolver_provider: Any,
        settings_provider: Any,
        nonce_store_provider: Any | None = None,
        protected_patterns: Iterable[str] = (
            r"^/v2/decide(?:/|$)",
            r"^/v2/rule/test(?:/|$)",
            r"^/v2/sdk/",
        ),
    ) -> None:
        super().__init__(app)
        self._resolver_provider = resolver_provider
        self._settings_provider = settings_provider
        self._nonce_store_provider = nonce_store_provider
        self._patterns = [re.compile(p) for p in protected_patterns]

    def _needs_guard(self, path: str) -> bool:
        return any(p.search(path) for p in self._patterns)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.method == "OPTIONS" or not self._needs_guard(request.url.path):
            return await call_next(request)

        settings = self._settings_provider()

        if not settings.app_key_required:
            raw_key = extract_api_key(request, header_name=settings.app_key_header) or ""
            request.state.resolved_app_key = ResolvedAppKey(site_id=0, api_key=raw_key)
            return await call_next(request)

        api_key = extract_api_key(request, header_name=settings.app_key_header)
        if not api_key:
            return _auth_failure_response(request, "缺少 API Key")

        try:
            resolver = self._resolver_provider()
            credential = await resolver.resolve_credential(api_key)
        except Exception as exc:  # pragma: no cover - Redis 异常兜底
            _logger.error("app_key_resolve_error", error=str(exc))
            return _auth_failure_response(request, "API Key 校验失败", code="APP_KEY_RESOLVE_ERROR")

        if credential is None:
            return _auth_failure_response(request, "API Key 无效或已失效")

        verified = False
        if getattr(settings, "signature_required", False):
            check = await verify_request_signature(
                request,
                credential,
                nonce_store=self._nonce_store_provider() if self._nonce_store_provider else None,
                window=getattr(settings, "signature_window", DEFAULT_TIMESTAMP_WINDOW),
            )
            if not check.ok:
                _logger.warning(
                    "request_signature_rejected",
                    site_id=credential.site_id,
                    reason=check.reason,
                    path=request.url.path,
                )
                # 与 Key 失效共用同一文案：不告诉探测方是哪一步没过。
                return _auth_failure_response(request, "API Key 无效或已失效")
            verified = True

        request.state.resolved_app_key = ResolvedAppKey(
            site_id=credential.site_id,
            api_key=api_key,
            signature_verified=verified,
        )
        return await call_next(request)


def _auth_failure_response(
    request: Request,
    message: str,
    *,
    code: str = "AUTH_UNAUTHENTICATED",
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return JSONResponse(
        status_code=401,
        content={
            "code": code,
            "message": message,
            "details": {},
            "request_id": request_id,
        },
    )


async def require_app_key(request: Request) -> ResolvedAppKey:
    """FastAPI 依赖：从 :class:`AppKeyEnforcementMiddleware` 已写入的 state 中取结果。

    若 middleware 未生效（例如未挂载），会尝试即时校验，保证行为一致。
    """
    resolved: ResolvedAppKey | None = getattr(request.state, "resolved_app_key", None)
    if resolved is not None:
        return resolved

    # 兜底路径：middleware 未介入（如本地脚本直接调用 decide 依赖）。
    from src.interfaces.http.dependencies import (
        get_app_key_resolver,
        get_gateway_settings,
        get_nonce_store,
    )

    settings = get_gateway_settings()

    if not settings.app_key_required:
        raw_key = extract_api_key(request, header_name=settings.app_key_header) or ""
        return ResolvedAppKey(site_id=0, api_key=raw_key)

    api_key = extract_api_key(request, header_name=settings.app_key_header)
    if not api_key:
        raise AuthenticationException("缺少 API Key")

    credential = await get_app_key_resolver().resolve_credential(api_key)
    if credential is None:
        raise AuthenticationException("API Key 无效或已失效")

    if getattr(settings, "signature_required", False):
        # 必须传 nonce_store：漏传会让 verify_request_signature 跳过整段重放校验，
        # 只剩 HMAC + 时间戳——攻击者可在时间窗内无限重放同一个合法签名请求。
        check = await verify_request_signature(
            request,
            credential,
            window=getattr(settings, "signature_window", DEFAULT_TIMESTAMP_WINDOW),
            nonce_store=get_nonce_store(),
        )
        if not check.ok:
            _logger.warning(
                "request_signature_rejected",
                site_id=credential.site_id,
                reason=check.reason,
                path=request.url.path,
            )
            raise AuthenticationException("API Key 无效或已失效")

    return ResolvedAppKey(
        site_id=credential.site_id,
        api_key=api_key,
        signature_verified=bool(getattr(settings, "signature_required", False)),
    )


__all__ = [
    "AppCredential",
    "AppKeyResolver",
    "AppKeyEnforcementMiddleware",
    "ResolvedAppKey",
    "SignatureCheck",
    "extract_api_key",
    "require_app_key",
    "verify_request_signature",
]

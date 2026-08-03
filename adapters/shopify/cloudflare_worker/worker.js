/**
 * Fangyu Defense — Shopify / Cloudflare Workers adapter
 * ======================================================
 *
 * Deploy as a Cloudflare Worker sitting in front of your Shopify storefront.
 * The Worker intercepts every request, sends a signed decision request to the
 * Fangyu V2 gateway, and executes the returned disposition.
 *
 * Configuration via Cloudflare Worker environment variables / secrets:
 *   FANGYU_GATEWAY_URL  e.g. https://defense.example.com
 *   FANGYU_SITE_ID      站点 ID，格式 site_<hex8>，同时用作 X-App-Key 请求头
 *   FANGYU_APP_SECRET   HMAC 验签密钥（明文写在此处或用 wrangler secret 管理均可）
 *   FANGYU_FAIL_MODE    "open"（默认）或 "closed"
 *
 * wrangler.toml 示例：
 *   [vars]
 *   FANGYU_GATEWAY_URL = "https://defense.example.com"
 *   FANGYU_SITE_ID     = "site_xxxxxxxx"
 *   FANGYU_APP_SECRET  = "your_app_secret_here"
 *   FANGYU_FAIL_MODE   = "open"
 *
 * Signing parity
 * --------------
 * buildSignPayload() is a direct port of client-sdk/src/core/signer.ts.
 * Cross-language correctness is locked by client-sdk/tests/fixtures/sign_vectors.json.
 * encodeURIComponent is used directly — it matches the Python/PHP/TS implementations
 * for all characters in the safe set (-_.!~*'()).
 */

// ── Signing ──────────────────────────────────────────────────────────────────

const EXCLUDED_KEYS = new Set(['sign']);

/**
 * Deep-sort object keys for canonical JSON serialisation.
 * Lists are order-preserved; only object keys are sorted.
 *
 * @param {unknown} value
 * @returns {unknown}
 */
function sortDeep(value) {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value !== null && typeof value === 'object') {
    const src = /** @type {Record<string,unknown>} */ (value);
    const sorted = /** @type {Record<string,unknown>} */ ({});
    for (const key of Object.keys(src).sort()) {
      if (src[key] !== undefined) sorted[key] = sortDeep(src[key]);
    }
    return sorted;
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(sortDeep(value));
}

function signValue(value) {
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (value !== null && typeof value === 'object') return canonicalJson(value);
  return String(value);
}

function buildSignPayload(params) {
  const parts = [];
  for (const key of Object.keys(params).sort()) {
    if (EXCLUDED_KEYS.has(key)) continue;
    const value = params[key];
    if (value === null || value === undefined || value === '') continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(signValue(value))}`);
  }
  return parts.join('&');
}

/**
 * Compute HMAC-SHA256 using the Web Crypto API (available in all Workers runtimes).
 *
 * @param {string} secret
 * @param {string} message
 * @returns {Promise<string>} lowercase hex digest
 */
async function hmacSha256(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function nonce() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function signBody(body, secret) {
  body.timestamp = Math.floor(Date.now() / 1000);
  body.nonce = nonce();
  body.sign = await hmacSha256(secret, buildSignPayload(body));
  return body;
}

// ── Gateway call ─────────────────────────────────────────────────────────────

const DECIDE_PATH = '/v2/decide';
const GATEWAY_TIMEOUT_MS = 3000;

/**
 * @param {object} context  Visitor context.
 * @param {object} env      Cloudflare Worker env bindings.
 * @returns {Promise<object|null>}
 */
async function gatewayDecide(context, env) {
  const gatewayUrl = (env.FANGYU_GATEWAY_URL || '').replace(/\/$/, '');
  const siteId     = env.FANGYU_SITE_ID || '';
  const appSecret  = env.FANGYU_APP_SECRET || '';

  if (!gatewayUrl || !siteId || !appSecret) return null;

  const body = await signBody({ context, requireDetails: false }, appSecret);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);

  let res;
  try {
    res = await fetch(gatewayUrl + DECIDE_PATH, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'X-App-Key': siteId,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) return null;

  let data;
  try { data = await res.json(); } catch { return null; }

  // Support both wrapped { data: {...} } and bare { verdict, mechanism, ... } shapes.
  return (data && typeof data.data === 'object' && data.data) ? data.data : data;
}

// ── SDK 注入 ─────────────────────────────────────────────────────────────────

/**
 * 生成服务端会话 token，用于关联第一层（Worker 决策）和第二层（SDK 指纹）。
 * 格式：sst_<hex32>，不可猜测，不携带敏感信息。
 */
function serverSessionToken() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return 'sst_' + Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * 向 HTML 响应的 <head> 注入 SDK 配置脚本 + SDK loader。
 * 使用 HTMLRewriter 流式处理，不缓冲完整响应体。
 *
 * 注入内容：
 *   window.__fy_server_ctx = { siteId, serverVerdict, serverToken, gatewayUrl }
 *   <script src="...sdk.min.js" defer></script>
 *   <script>/* SDK onDecision handler *\/</script>
 *
 * @param {Response} originResponse   来自源站的原始响应。
 * @param {object}   env              Worker env bindings.
 * @param {object}   serverDecision   第一层决策结果（verdict, mechanism）。
 * @param {string}   serverToken      服务端会话 token.
 * @returns {Response}
 */
function injectSdk(originResponse, env, serverDecision, serverToken) {
  const siteId     = env.FANGYU_SITE_ID    || '';
  const gatewayUrl = (env.FANGYU_GATEWAY_URL || '').replace(/\/$/, '');
  const sdkSrc     = env.FANGYU_SDK_URL    || `${gatewayUrl}/sdk/fangyu-sdk.min.js`;
  const blockedUrl = env.FANGYU_BLOCKED_URL || '/blocked';
  const challengeUrl = env.FANGYU_CHALLENGE_URL || '/challenge';

  const snippet = `
<script>
window.__fy_server_ctx = ${JSON.stringify({
    siteId,
    gatewayUrl,
    serverVerdict: serverDecision?.verdict || 'unknown',
    serverToken,
    blockedUrl,
    challengeUrl,
  })};
</script>
<script src="${sdkSrc}" defer></script>
<script>
document.addEventListener('DOMContentLoaded', function () {
  var ctx = window.__fy_server_ctx || {};
  // 缓存命中：已知 hostile 直接跳（同一 session 内二次导航）。
  // 存 {v, exp} 而非裸 verdict，过期即视为未命中，使 ttlSeconds 真正生效。
  var _c = null;
  try { _c = JSON.parse(sessionStorage.getItem('_fy_v') || 'null'); } catch (e) {}
  if (_c && _c.exp > Date.now() && _c.v === 'hostile') {
    location.replace(ctx.blockedUrl || '/blocked');
    return;
  }
  if (typeof SdSdk === 'undefined') return;  // SDK 加载失败时静默放行
  SdSdk.protect({
    gatewayUrl:      ctx.gatewayUrl,
    siteId:          ctx.siteId,
    serverToken:     ctx.serverToken,   // 网关用此字段关联服务端预判
    autoApply:       false,
    collectBehavior: true,
    onDecision: function (d) {
      sessionStorage.setItem('_fy_v', JSON.stringify({
        v: d.verdict, exp: Date.now() + (d.ttlSeconds || 300) * 1000
      }));
      if (d.mechanism === 'redirect') {
        location.replace(d.target && d.target.url ? d.target.url : ctx.blockedUrl);
      } else if (d.mechanism === 'challenge') {
        location.replace(ctx.challengeUrl + '?next=' + encodeURIComponent(location.href));
      } else if (d.mechanism === 'deny') {
        document.documentElement.innerHTML =
          '<body style="font:sans-serif;text-align:center;padding:80px"><h1>403</h1></body>';
      }
    }
  });
});
</script>`.trim();

  return new HTMLRewriter()
    .on('head', {
      element(el) { el.append(snippet, { html: true }); }
    })
    .transform(originResponse);
}



const SAFE_REDIRECT_RE = /^https?:\/\//i;

/**
 * Convert a gateway decision payload into a Cloudflare Worker Response.
 *
 * @param {object|null} payload   Gateway response or null (gateway unreachable).
 * @param {Request} request       Original incoming request.
 * @param {object} env            Worker env.
 * @returns {Response|null}       null → pass through to origin.
 */
function executeDecision(payload, request, env) {
  if (!payload) {
    // Gateway unreachable.
    const failMode = (env.FANGYU_FAIL_MODE || 'open');
    return failMode === 'closed' ? new Response('Forbidden', { status: 403 }) : null;
  }

  const mech = payload.mechanism || 'pass';

  switch (mech) {
    case 'pass':
      return null; // let the request through

    case 'redirect': {
      const url = payload.targetUrl;
      if (url && SAFE_REDIRECT_RE.test(url)) {
        const status = (payload.httpStatus >= 300 && payload.httpStatus < 400)
          ? payload.httpStatus : 302;
        return Response.redirect(url, status);
      }
      return new Response('Forbidden', { status: 403 });
    }

    case 'not_found': {
      const status = payload.httpStatus || 404;
      return payload.targetKind === 'status_only'
        ? new Response(null, { status })
        : new Response('Not Found', { status });
    }

    case 'deny': {
      const status = payload.httpStatus || 403;
      return payload.targetKind === 'status_only'
        ? new Response(null, { status })
        : new Response('Forbidden', { status });
    }

    case 'serve_alt':
    case 'challenge': {
      const content = payload.pageContent;
      if (content) {
        return new Response(content, {
          status: 200,
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        });
      }
      return new Response('Forbidden', { status: 403 });
    }

    default: {
      // 未知机制：记 WARN 日志，按 fail_mode 决策
      console.warn('[fangyu] unknown mechanism:', mech, 'fail_mode=', env.FANGYU_FAIL_MODE || 'open');
      const failMode = env.FANGYU_FAIL_MODE || 'open';
      return failMode === 'closed' ? new Response('Forbidden', { status: 403 }) : null;
    }
  }
}

// ── Visitor context ───────────────────────────────────────────────────────────

/**
 * Extract visitor context from the incoming Cloudflare request.
 *
 * CF-Connecting-IP is set by Cloudflare's own edge and cannot be forged
 * by the client (unlike X-Forwarded-For), so it is safe to trust here.
 * X-Forwarded-For is deliberately not read.
 *
 * @param {Request} request
 * @param {object} env
 * @returns {object}
 */
function buildContext(request, env) {
  const url = new URL(request.url);

  // Cloudflare Workers always set CF-Connecting-IP for proxied requests.
  const ip = request.headers.get('CF-Connecting-IP') || '0.0.0.0';

  const context = {
    ingress: 'adapter',
    ip,
    visitUrl: request.url,
    userAgent: request.headers.get('User-Agent') || '',
  };

  // Read evercookie repeat value from cookie (key _sd_0000).
  const cookieHeader = request.headers.get('Cookie') || '';
  const match = cookieHeader.match(/(?:^|;\s*)_sd_0000=([^;]+)/);
  if (match) {
    context.fingerprint = decodeURIComponent(match[1]);
    context.repeatKey   = '_sd_0000';
    context.repeatValue = context.fingerprint;
  }

  // Referer — omit if it's the same host (internal navigation).
  const referer = request.headers.get('Referer') || '';
  if (referer && !referer.includes(url.host)) {
    context.referer = referer;
  }

  return context;
}

// ── Worker entry point ────────────────────────────────────────────────────────

export default {
  /**
   * @param {Request} request
   * @param {object} env
   * @param {ExecutionContext} ctx
   * @returns {Promise<Response>}
   */
  async fetch(request, env, ctx) {
    // 跳过静态资源和 Shopify 管理路径
    const url = new URL(request.url);
    if (
      url.pathname.startsWith('/admin') ||
      url.pathname.startsWith('/payments') ||
      url.pathname.startsWith('/checkouts') ||
      /\.(css|js|png|jpg|jpeg|gif|svg|woff2?|ttf|ico|map)$/i.test(url.pathname)
    ) {
      return fetch(request);
    }

    const context     = buildContext(request, env);
    const serverToken = serverSessionToken();
    // 通过 context.extra 传递 serverToken，gateway DecisionContext.extra 字段接收
    context.extra = { serverToken };

    const payload  = await gatewayDecide(context, env);
    const blocked  = executeDecision(payload, request, env);

    // 第一层判定为 hostile/deny/redirect → 直接返回，SDK 永不加载
    if (blocked) return blocked;

    // 第一层 pass（含网关不可达的 fail-open）→ 放行并注入 SDK
    const htmlMode = env.FANGYU_SDK_INJECT !== 'false';   // 默认开启注入
    const originResp = await fetch(request);

    // 只对 HTML 内容注入，图片、JSON 等直接透传
    const ct = originResp.headers.get('content-type') || '';
    if (!htmlMode || !ct.includes('text/html')) {
      return originResp;
    }

    return injectSdk(originResp, env, payload, serverToken);
  },
};

--[[
  Fangyu Defense — Nginx / OpenResty adapter
  ============================================
  Drop this file into your OpenResty config and wire it via access_by_lua_file:

    location / {
        access_by_lua_file /path/to/defense.lua;
        proxy_pass http://upstream;
    }

  Dependencies (available in any OpenResty bundle ≥ 1.21):
    lua-resty-http    — ngx.location.capture alternative for subrequests
    lua-resty-hmac    — or use resty.openssl.hmac (OpenResty 1.25+)
    lua-cjson         — bundled with OpenResty

  Configuration via nginx.conf set directives (or environment / secrets manager):
    set $fangyu_gateway_url  "https://defense.example.com";
    set $fangyu_site_id      "site_xxxxxxxx";   -- 站点 ID，同时用作 X-App-Key
    set $fangyu_app_secret   "your_app_secret";
    set $fangyu_fail_mode    "open";            -- "open" or "closed"
    set $fangyu_sdk_inject   "on";              -- "on"(默认) 或 "off"
    set $fangyu_sdk_url      "";                -- SDK URL，空=自动用 gateway_url/sdk/fangyu-sdk.min.js
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";

  Signing parity
  --------------
  The build_payload() function below must produce byte-identical output to:
    Python  fangyu_shared.security.signing.build_sign_payload
    TS      client-sdk/src/core/signer.ts :: buildSignPayload
    PHP     class-fangyu-signer.php       :: build_payload
  All four are validated by client-sdk/tests/fixtures/sign_vectors.json.

  Verified encoding edge cases (matching encodeURIComponent, NOT rawurlencode):
    !  →  !      (RFC3986 would give %21)
    *  →  *      (RFC3986 would give %2A)
    '  →  '      (RFC3986 would give %27)
    (  →  (      (RFC3986 would give %28)
    )  →  )      (RFC3986 would give %29)
    /  →  %2F
       →  %20   (not +)
--]]

local cjson  = require "cjson.safe"
local resty_hmac = nil
-- OpenResty 1.25+ ships resty.openssl.hmac; older builds use lua-resty-hmac.
-- We attempt both; fail loudly if neither is available rather than silently
-- computing wrong signatures.
local ok, mod = pcall(require, "resty.openssl.hmac")
if ok then
  resty_hmac = mod
else
  ok, mod = pcall(require, "resty.hmac")
  if ok then resty_hmac = mod end
end
if not resty_hmac then
  ngx.log(ngx.CRIT, "[fangyu] neither resty.openssl.hmac nor resty.hmac found")
  -- fail-open: let the request through rather than crash the server
  return
end

local http = require "resty.http"

-- ── Config ──────────────────────────────────────────────────────────────────

local function cfg(key, default)
  local v = ngx.var["fangyu_" .. key]
  if v == nil or v == "" then return default end
  return v
end

local GATEWAY_URL  = cfg("gateway_url", "")
local SITE_ID      = cfg("site_id", "")
-- 浏览器 SDK 需要数值型 appId（SdkConfig.appId 校验 `Number.isInteger && > 0`）。
-- SITE_ID 是字符串键，只能作 X-App-Key，不能充当 appId。
local APP_ID       = tonumber(cfg("app_id", "0")) or 0
local APP_SECRET   = cfg("app_secret", "")
local FAIL_MODE    = cfg("fail_mode", "open")
local SDK_INJECT   = cfg("sdk_inject", "on")
local SDK_URL      = cfg("sdk_url", "")
local BLOCKED_URL  = cfg("blocked_url", "/blocked")
local CHALLENGE_URL = cfg("challenge_url", "/challenge")

-- ── Signing ──────────────────────────────────────────────────────────────────

-- Characters NOT encoded by encodeURIComponent (beyond A-Za-z0-9):
local SAFE_CHARS = {
  ["-"] = true, ["_"] = true, ["."] = true, ["!"] = true,
  ["~"] = true, ["*"] = true, ["'"] = true, ["("] = true, [")"] = true,
}

local function encode_component(s)
  s = tostring(s)
  return (s:gsub("[^A-Za-z0-9%-_.!~*'()]", function(c)
    return string.format("%%%02X", string.byte(c))
  end))
end

-- Deep-sort an object's keys (lists are preserved in order).
-- Returns a new table ready for cjson.encode.
local function sort_deep(val)
  local t = type(val)
  if t == "table" then
    -- Detect list vs object: a list has only integer keys 1..n.
    local is_list = true
    local n = #val
    for k, _ in pairs(val) do
      if type(k) ~= "number" or k < 1 or k > n or k ~= math.floor(k) then
        is_list = false
        break
      end
    end
    if is_list then
      local out = {}
      for i, v in ipairs(val) do out[i] = sort_deep(v) end
      return out
    else
      -- Object: collect & sort keys
      local keys = {}
      for k in pairs(val) do keys[#keys+1] = tostring(k) end
      table.sort(keys)
      -- cjson needs a special marker to emit {} not []; use cjson.empty_array trick
      -- workaround: rebuild as a plain table with sorted keys stored in metatable order
      -- Actually cjson.encode on a table with mixed / non-sequential keys emits object.
      local out = {}
      for _, k in ipairs(keys) do
        if val[k] ~= nil then
          out[k] = sort_deep(val[k])
        end
      end
      return out
    end
  end
  return val
end

local function canonical_json(val)
  local sorted = sort_deep(val)
  return cjson.encode(sorted)
end

local function stringify_value(val)
  local t = type(val)
  if t == "boolean" then
    return val and "true" or "false"
  elseif t == "table" then
    return canonical_json(val)
  else
    return tostring(val)
  end
end

local EXCLUDED_KEYS = { sign = true }

local function build_payload(params)
  -- collect and sort keys
  local keys = {}
  for k in pairs(params) do keys[#keys+1] = tostring(k) end
  table.sort(keys)

  local parts = {}
  for _, k in ipairs(keys) do
    if not EXCLUDED_KEYS[k] then
      local v = params[k]
      if v ~= nil and v ~= "" then
        -- false (boolean) must be kept; only nil and "" are dropped.
        parts[#parts+1] = encode_component(k) .. "=" .. encode_component(stringify_value(v))
      end
    end
  end
  return table.concat(parts, "&")
end

local function compute_hmac(secret, message)
  -- resty.openssl.hmac API
  if resty_hmac.new then
    local h, err = resty_hmac.new(secret, "sha256")
    if not h then
      ngx.log(ngx.ERR, "[fangyu] hmac init error: ", err)
      return nil
    end
    h:update(message)
    local digest = h:final()
    -- convert binary to hex
    return (digest:gsub(".", function(c)
      return string.format("%02x", string.byte(c))
    end))
  end
  -- lua-resty-hmac API (older)
  local h = resty_hmac:new(secret, resty_hmac.ALGOS.SHA256)
  if not h then return nil end
  h:update(message)
  return h:final(nil, true) -- hex
end

local function nonce()
  -- 16 random bytes → 32 hex chars
  local bytes = {}
  for i = 1, 16 do bytes[i] = string.format("%02x", math.random(0, 255)) end
  return table.concat(bytes)
end

local function sign_body(body, secret)
  body.timestamp = ngx.time()
  body.nonce     = nonce()
  body.sign      = compute_hmac(secret, build_payload(body))
  return body
end

-- ── Gateway call ─────────────────────────────────────────────────────────────

local function decide(context)
  if GATEWAY_URL == "" or SITE_ID == "" or APP_SECRET == "" then
    return nil, "not_configured"
  end

  local body_tbl = {
    context        = context,
    requireDetails = false,
  }
  sign_body(body_tbl, APP_SECRET)

  local body_str, encode_err = cjson.encode(body_tbl)
  if not body_str then
    return nil, "json_encode: " .. (encode_err or "?")
  end

  local httpc = http.new()
  httpc:set_timeout(3000) -- 3 s

  local res, err = httpc:request_uri(GATEWAY_URL .. "/v2/decide", {
    method  = "POST",
    headers = {
      ["Content-Type"] = "application/json; charset=utf-8",
      ["X-App-Key"]    = SITE_ID,
    },
    body = body_str,
  })

  if not res or res.status < 200 or res.status >= 300 then
    return nil, err or ("http " .. (res and res.status or "?"))
  end

  local data, derr = cjson.decode(res.body)
  if not data then return nil, "json_decode: " .. (derr or "?") end

  -- Support wrapped { data: {...} } and bare {...} shapes.
  local payload = (data.data and type(data.data) == "table") and data.data or data
  return payload, nil
end

-- ── Disposition execution ─────────────────────────────────────────────────────

local function execute(payload)
  if not payload then return end
  local mech = payload.mechanism or "pass"

  if mech == "pass" then
    return  -- allow
  elseif mech == "redirect" then
    local url = payload.targetUrl
    if url and (url:sub(1,7) == "http://" or url:sub(1,8) == "https://") then
      local status = tonumber(payload.httpStatus) or 302
      if status < 300 or status >= 400 then status = 302 end
      return ngx.redirect(url, status)
    end
    -- No valid URL → fall through to deny
    ngx.exit(403)
  elseif mech == "not_found" then
    local status = tonumber(payload.httpStatus) or 404
    if payload.targetKind == "status_only" then
      ngx.status = status
      return ngx.exit(ngx.HTTP_OK)
    end
    ngx.exit(status)
  elseif mech == "deny" then
    local status = tonumber(payload.httpStatus) or 403
    if payload.targetKind == "status_only" then
      ngx.status = status
      return ngx.exit(ngx.HTTP_OK)
    end
    ngx.exit(status)
  elseif mech == "serve_alt" or mech == "challenge" then
    local content = payload.pageContent
    if content and content ~= "" then
      ngx.header["Content-Type"] = "text/html; charset=utf-8"
      ngx.status = 200
      ngx.say(content)
      return ngx.exit(ngx.HTTP_OK)
    end
    ngx.exit(403)
  else
    -- 未知机制：记 WARN 日志，按 fail_mode 决策
    ngx.log(ngx.WARN, "[fangyu] unknown mechanism: ", mech, ", fail_mode=", FAIL_MODE)
    if FAIL_MODE == "closed" then
      ngx.exit(403)
    end
    -- fail_mode=open 时放行（兜底行为）
  end
end

-- ── SDK 注入 ─────────────────────────────────────────────────────────────────

-- 生成服务端 session token（16字节随机十六进制）
local function server_session_token()
  local bytes = {}
  math.randomseed(ngx.now() * 1000 + ngx.worker.pid())
  for i = 1, 16 do bytes[i] = string.format("%02x", math.random(0, 255)) end
  return "sst_" .. table.concat(bytes)
end

-- 向 HTML 响应体注入 SDK snippet（仅当 Content-Type 含 text/html 时调用）
local function build_sdk_snippet(server_verdict, server_token)
  local sdk_src = SDK_URL ~= "" and SDK_URL
    or (GATEWAY_URL .. "/sdk/fangyu-sdk.min.js")

  -- 键名必须与 SdkConfig 对齐：apiBase / apiKey / appId。
  -- 旧的 gatewayUrl / siteId 在 SDK 里不存在，validateConfig() 会直接抛错。
  local ctx_json = cjson.encode({
    apiBase       = GATEWAY_URL,
    apiKey        = SITE_ID,
    appId         = APP_ID,
    serverVerdict = server_verdict or "unknown",
    serverToken   = server_token,
    blockedUrl    = BLOCKED_URL,
    challengeUrl  = CHALLENGE_URL,
  })

  return string.format([[
<script>
window.__fy_server_ctx = %s;
</script>
<script src="%s" defer></script>
<script>
document.addEventListener('DOMContentLoaded', function () {
  var ctx = window.__fy_server_ctx || {};
  // 缓存读取：过期即视为未命中，让 SDK 重新走一次决策。
  // 存 {v, exp} 而非裸 verdict 是为了让后台配的 ttlSeconds 在边缘侧真正生效。
  var _c = null;
  try { _c = JSON.parse(sessionStorage.getItem('_fy_v') || 'null'); } catch (e) {}
  if (_c && _c.exp > Date.now() && _c.v === 'hostile') {
    location.replace(ctx.blockedUrl || '/blocked'); return;
  }
  if (typeof SdSdk === 'undefined') return;
  if (!ctx.apiBase || !ctx.apiKey || !ctx.appId) return;
  // protect() 返回 Promise<{decision, applied}>；SDK 没有 onDecision 配置项，
  // 处置回调只能从这里取。autoApply:false 时由下面的分支自行执行。
  SdSdk.protect({
    apiBase: ctx.apiBase, apiKey: ctx.apiKey, appId: ctx.appId,
    serverToken: ctx.serverToken || '', autoApply: false, collectBehavior: true
  }).then(function (outcome) {
    var d = outcome && outcome.decision;
    if (!d) return;
    sessionStorage.setItem('_fy_v', JSON.stringify({
      v: d.verdict, exp: Date.now() + (d.ttlSeconds || 300) * 1000
    }));
    if (d.mechanism === 'redirect') {
      location.replace(d.targetUrl || ctx.blockedUrl);
    } else if (d.mechanism === 'challenge') {
      location.replace(ctx.challengeUrl + '?next=' + encodeURIComponent(location.href));
    } else if (d.mechanism === 'deny') {
      document.documentElement.innerHTML =
        '<body style="font:sans-serif;text-align:center;padding:80px"><h1>403</h1></body>';
    }
  }).catch(function () { /* SDK 异常不影响页面 */ });
});
</script>
]], ctx_json, sdk_src)
end



-- ── Main ─────────────────────────────────────────────────────────────────────

-- Skip Nginx internal redirects.
if ngx.req.is_internal() then return end

local real_ip = ngx.var.remote_addr or "0.0.0.0"
if ngx.var.http_cf_connecting_ip and ngx.var.http_cf_connecting_ip ~= "" then
  real_ip = ngx.var.http_cf_connecting_ip
end

local server_token = server_session_token()

local context = {
  siteId    = SITE_ID,
  ingress   = "adapter",
  ip        = real_ip,
  visitUrl  = ngx.var.scheme .. "://" .. ngx.var.host .. ngx.var.request_uri,
  -- path / method 必须显式上报：规则引擎的 request.path 直接取该字段，不从
  -- visitUrl 派生。漏报会让「敏感路径阻断」这类规则永不命中，而否定条件
  -- （路径不在白名单则拦截）反而会因取值恒为 "/" 而误拦全站。
  -- uri 不含 query string，正是规则需要的路径部分。
  path      = ngx.var.uri or "/",
  method    = ngx.var.request_method or "GET",
  userAgent = ngx.var.http_user_agent or "",
  -- serverToken 通过 extra 字段传递，匹配 gateway DecisionContext.extra
  extra     = { serverToken = server_token },
}

local repeat_val = ngx.var.cookie__sd_0000
if repeat_val and repeat_val ~= "" then
  context.fingerprint = repeat_val
  context.repeatKey   = "_sd_0000"
  context.repeatValue = repeat_val
end

local payload, err = decide(context)
if err then
  ngx.log(ngx.WARN, "[fangyu] gateway error: ", err)
  if FAIL_MODE == "closed" then ngx.exit(403) end
  -- fail-open：继续执行，SDK 仍然注入
end

-- 第一层判定为拦截时直接执行（SDK 不加载）
if payload and payload.mechanism ~= "pass" then
  execute(payload)
  return
end

-- 第一层 pass（或网关不可达）→ 注入 SDK 到响应 HTML
-- 使用 header_filter + body_filter 阶段实现；
-- 此处设置一个共享变量，由 body_filter_by_lua_block 读取并追加 snippet。
if SDK_INJECT ~= "off" then
  local server_verdict = payload and payload.verdict or "unknown"
  ngx.ctx.fy_sdk_snippet = build_sdk_snippet(server_verdict, server_token)
end

--[[
── nginx.conf 配置示例（双层模式）───────────────────────────────────────────

  server {
    location / {
      # 第一层：access 阶段，决策+注入 snippet 写入 ngx.ctx
      access_by_lua_file /etc/nginx/lua/fangyu/defense.lua;

      proxy_pass http://upstream;

      # 第二层：body_filter 阶段，把 snippet 追加到 </head> 之前
      body_filter_by_lua_block {
        local snippet = ngx.ctx.fy_sdk_snippet
        if not snippet then return end
        -- 仅对 HTML 响应注入
        local ct = ngx.header["Content-Type"] or ""
        if not ct:find("text/html", 1, true) then return end
        -- 把 snippet 插入到 </head> 之前
        local chunk, eof = ngx.arg[1], ngx.arg[2]
        if chunk then
          ngx.arg[1] = chunk:gsub("</head>", snippet .. "</head>", 1)
        end
      }
    }
  }

注意：body_filter 方式在流式响应或分块传输时可能只命中第一个 chunk。
对于大多数业务场景（商品页、活动页）这已经足够。如需严格保证，
可在 proxy_pass 前加 proxy_buffering on; 强制缓冲完整响应体。
]]

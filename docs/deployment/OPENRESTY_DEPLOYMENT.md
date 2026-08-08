# OpenResty Lua 适配器部署指南

## 问题排查清单

### 1. 验证 OpenResty 环境

```bash
# 检查 OpenResty 版本（需要 ≥ 1.21）
openresty -v

# 确认 Lua 模块路径
openresty -V 2>&1 | grep -o 'prefix=[^ ]*'
openresty -V 2>&1 | grep -o 'conf-path=[^ ]*'

# 检查必需的 Lua 模块是否存在
find /usr/local/openresty -name "resty" -type d
ls -la /usr/local/openresty/lualib/resty/ | grep -E '(http|hmac|cjson)'
```

**预期输出**:
- `openresty/1.21.4.x` 或更高
- 应该看到 `http.lua`, `hmac.lua`, `cjson.so`

---

## 2. 1Panel 专属配置

### 2.1 文件放置位置

1Panel 的 OpenResty 配置通常在:
```
/opt/1panel/apps/openresty/<version>/conf/
/opt/1panel/apps/openresty/<version>/www/sites/<your-site>/
```

**Lua 脚本正确路径**:
```bash
# 创建 Lua 脚本目录
mkdir -p /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/

# 复制脚本
cp adapters/nginx-lua/defense.lua \
   /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua

# 设置权限
chmod 644 /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua
chown www:www /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua
```

### 2.2 Nginx 配置（1Panel 界面配置）

在 1Panel → 网站 → 你的站点 → 配置文件,找到 `server {}` 块,添加:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # ═══════════════════════════════════════════════════════════════
    # Fangyu 配置变量（必须在 server 块内）
    # ═══════════════════════════════════════════════════════════════
    set $fangyu_gateway_url  "https://your-gateway.example.com";
    set $fangyu_site_id      "site_xxxxxxxx";        # 站点 ID
    set $fangyu_app_id       "12345";                # 必须是数值,SDK 需要
    set $fangyu_app_secret   "your_app_secret_here";
    set $fangyu_fail_mode    "open";                 # open 或 closed
    set $fangyu_sdk_inject   "on";                   # on 或 off
    set $fangyu_sdk_url      "";                     # 空=自动使用 gateway/sdk/fangyu-sdk.min.js
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";

    location / {
        # ═══════════════════════════════════════════════════════════
        # 第一层：access 阶段调用防御脚本
        # ═══════════════════════════════════════════════════════════
        access_by_lua_file /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua;

        # 你的原有配置（静态文件或反代）
        root /opt/1panel/apps/openresty/openresty/www/sites/your-site;
        index index.html index.htm;
        try_files $uri $uri/ /index.html;

        # 或者如果是反向代理
        # proxy_pass http://your-upstream;
        # proxy_set_header Host $host;
        # proxy_set_header X-Real-IP $remote_addr;

        # ═══════════════════════════════════════════════════════════
        # 第二层：body_filter 阶段注入 SDK
        # ═══════════════════════════════════════════════════════════
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

    # 拦截页（可选,根据你的 blocked_url 配置）
    location = /blocked {
        return 403 '<html><body><h1>访问被拦截</h1><p>请联系管理员</p></body></html>';
        add_header Content-Type "text/html; charset=utf-8";
    }

    location = /challenge {
        return 200 '<html><body><h1>安全验证</h1><p>正在验证...</p></body></html>';
        add_header Content-Type "text/html; charset=utf-8";
    }
}
```

---

## 3. 测试步骤

### 3.1 语法检查

```bash
# 测试配置文件语法
openresty -t

# 如果报错 "lua_code_cache is off"，确保生产环境设置为 on
grep -r "lua_code_cache" /opt/1panel/apps/openresty/openresty/conf/
```

**预期输出**:
```
nginx: the configuration file /path/to/nginx.conf syntax is ok
nginx: configuration file /path/to/nginx.conf test is successful
```

### 3.2 重载配置

```bash
# 1Panel 界面操作
# 网站 → 你的站点 → 重启

# 或命令行
systemctl reload openresty

# 检查进程
ps aux | grep openresty
```

### 3.3 查看日志（关键）

```bash
# 错误日志位置（1Panel 默认）
tail -f /opt/1panel/apps/openresty/openresty/logs/error.log

# 访问日志
tail -f /opt/1panel/apps/openresty/openresty/logs/access.log

# 或站点专属日志
tail -f /opt/1panel/apps/openresty/openresty/www/sites/<your-site>/logs/error.log
```

**查找关键信息**:
```bash
# 筛选 Fangyu 相关日志
grep -i fangyu /opt/1panel/apps/openresty/openresty/logs/error.log

# 查找 Lua 错误
grep -E "lua|pcall|module" /opt/1panel/apps/openresty/openresty/logs/error.log
```

### 3.4 手动测试请求

```bash
# 基础测试
curl -I http://your-domain.com/

# 带调试信息（查看响应头）
curl -v http://your-domain.com/ 2>&1 | grep -i "x-"

# 检查 HTML 是否包含 SDK 注入
curl -s http://your-domain.com/ | grep -o "window.__fy_server_ctx"
curl -s http://your-domain.com/ | grep -o "fangyu-sdk.min.js"
```

**预期结果**:
- 响应正常返回（如果配置 fail_mode=open）
- HTML 中应该包含 `<script>window.__fy_server_ctx = {...}</script>`
- 应该看到 SDK 脚本标签

---

## 4. 常见问题排查

### 问题 1: "module 'resty.hmac' not found"

**原因**: OpenResty 缺少 HMAC 模块

**解决**:
```bash
# 方法一：安装 lua-resty-openssl（OpenResty 1.25+）
cd /tmp
git clone https://github.com/fffonion/lua-resty-openssl.git
cd lua-resty-openssl
make install LUA_LIB_DIR=/usr/local/openresty/lualib

# 方法二：安装 lua-resty-hmac（兼容老版本）
cd /tmp
git clone https://github.com/jkeys089/lua-resty-hmac.git
cp -r lua-resty-hmac/lib/resty/* /usr/local/openresty/lualib/resty/

# 重启 OpenResty
systemctl restart openresty
```

### 问题 2: "attempt to call field 'new' (a nil value)"

**原因**: HMAC 模块存在但 API 不匹配

**调试**:
```lua
-- 在 defense.lua 第 60 行后添加调试日志
ngx.log(ngx.ERR, "[debug] resty_hmac type: ", type(resty_hmac))
if resty_hmac then
  for k, v in pairs(resty_hmac) do
    ngx.log(ngx.ERR, "[debug] resty_hmac.", k, " = ", type(v))
  end
end
```

重载后查看日志确认模块接口。

### 问题 3: SDK 脚本未注入

**检查点**:
1. 确认响应是 HTML（`Content-Type: text/html`）
2. 确认 `fangyu_sdk_inject` 为 `"on"`
3. 检查是否有 `</head>` 标签（单页应用可能没有）

**临时调试**:
```lua
-- 在 defense.lua 第 448 行后添加
ngx.log(ngx.ERR, "[debug] SDK inject enabled, snippet length: ", 
        ngx.ctx.fy_sdk_snippet and #ngx.ctx.fy_sdk_snippet or 0)
```

### 问题 4: 配置变量未生效

**验证**:
```lua
-- 在 defense.lua 第 83 行后添加
ngx.log(ngx.ERR, "[debug] GATEWAY_URL=", GATEWAY_URL, 
        " SITE_ID=", SITE_ID, " APP_ID=", APP_ID)
```

如果全是空值，说明 `set $fangyu_*` 不在正确的作用域。

**修复**: 确保 `set` 指令在 `server {}` 或 `location {}` 块内，不能在 `http {}` 块。

### 问题 5: Gateway 返回 401/403

**检查签名**:
```bash
# 在服务器上运行签名测试
cd "Evercookie Defense System V2"

# 创建临时测试脚本
cat > /tmp/test_lua_sign.lua << 'EOF'
package.path = package.path .. ";./adapters/nginx-lua/?.lua"
dofile("adapters/nginx-lua/defense.lua")

local secret = "test_secret_key"
local params = {
  context = {ip = "1.1.1.1"},
  timestamp = 1700000000,
  nonce = "aaaa",
}

local payload = build_payload(params)
local sign = compute_hmac(secret, payload)

print("Payload: " .. payload)
print("Sign: " .. sign)
EOF

lua /tmp/test_lua_sign.lua
```

对比输出与 Python 版本:
```bash
python3 << 'EOF'
from fangyu_shared.security.signing import build_sign_payload, sign_request
params = {
    "context": {"ip": "1.1.1.1"},
    "timestamp": 1700000000,
    "nonce": "aaaa",
}
payload = build_sign_payload(params)
from hashlib import sha256
import hmac
sign = hmac.new(b"test_secret_key", payload.encode(), sha256).hexdigest()
print(f"Payload: {payload}")
print(f"Sign: {sign}")
EOF
```

两者输出必须完全一致。

---

## 5. 生产部署检查清单

- [ ] OpenResty 版本 ≥ 1.21
- [ ] `resty.hmac` 或 `resty.openssl.hmac` 已安装
- [ ] `defense.lua` 文件权限 644
- [ ] `set $fangyu_*` 变量在正确的作用域
- [ ] `APP_ID` 是数值而非字符串
- [ ] `APP_SECRET` 与 Gateway 后台配置一致
- [ ] `openresty -t` 语法检查通过
- [ ] 错误日志无 `[fangyu]` 相关报错
- [ ] 测试请求返回预期状态码
- [ ] HTML 响应中包含 SDK 脚本
- [ ] `lua_code_cache on;`（生产环境必须开启）
- [ ] 日志轮转已配置（避免日志文件过大）

---

## 6. 性能优化建议

### 6.1 启用 Lua 代码缓存

```nginx
http {
    lua_code_cache on;  # 必须开启,否则性能极差
}
```

### 6.2 连接池优化

```nginx
http {
    lua_socket_pool_size 30;
    lua_socket_keepalive_timeout 60s;
}
```

### 6.3 共享字典缓存（高级）

```nginx
http {
    # 用于缓存 Gateway 决策结果
    lua_shared_dict fangyu_cache 10m;
}
```

在 `defense.lua` 中添加缓存逻辑:
```lua
local cache = ngx.shared.fangyu_cache
local cache_key = "decision:" .. real_ip
local cached = cache:get(cache_key)
if cached then
  -- 使用缓存结果,跳过 Gateway 调用
end
```

---

## 7. 监控指标

### 7.1 Nginx 日志格式

```nginx
log_format fangyu_log '$remote_addr - $remote_user [$time_local] '
                      '"$request" $status $body_bytes_sent '
                      '"$http_referer" "$http_user_agent" '
                      'fangyu_decision=$fangyu_decision '
                      'fangyu_latency=$fangyu_latency';

access_log /var/log/openresty/fangyu_access.log fangyu_log;
```

### 7.2 自定义变量（在 defense.lua 中添加）

```lua
-- 在 execute() 函数开始处
ngx.var.fangyu_decision = mech or "unknown"
ngx.var.fangyu_latency = string.format("%.3f", ngx.now() - ngx.req.start_time())
```

并在 nginx.conf 中声明:
```nginx
server {
    set $fangyu_decision "-";
    set $fangyu_latency "0";
}
```

---

## 8. 安全加固

### 8.1 隐藏敏感信息

```nginx
# 不要在错误页暴露 OpenResty 版本
server_tokens off;
more_clear_headers Server;
```

### 8.2 限流保护

```nginx
http {
    limit_req_zone $binary_remote_addr zone=fangyu_zone:10m rate=10r/s;
}

server {
    location / {
        limit_req zone=fangyu_zone burst=20 nodelay;
        access_by_lua_file .../defense.lua;
    }
}
```

### 8.3 Secret 管理

**不要硬编码在配置文件中**,使用环境变量:
```nginx
env FANGYU_APP_SECRET;

server {
    set_by_lua_block $fangyu_app_secret {
        return os.getenv("FANGYU_APP_SECRET") or ""
    }
}
```

---

## 9. 回滚方案

保留原配置备份:
```bash
cp /opt/1panel/apps/openresty/openresty/conf/nginx.conf \
   /opt/1panel/apps/openresty/openresty/conf/nginx.conf.backup.$(date +%Y%m%d)
```

快速禁用防御:
```nginx
location / {
    # 注释掉 Lua 调用
    # access_by_lua_file /path/to/defense.lua;

    # 或设置 fail_mode=open 让所有请求通过
    set $fangyu_fail_mode "open";
    set $fangyu_gateway_url "";  # 空 URL 会触发 not_configured 错误,直接放行
}
```

---

## 附录 A: 完整示例配置

见 `adapters/nginx-lua/examples/1panel-full-config.conf`

## 附录 B: 故障排查流程图

```
┌─ 访问网站无响应
│
├─ 检查 OpenResty 进程是否运行
│  └─ systemctl status openresty
│
├─ 检查错误日志
│  └─ tail -f error.log | grep -i "fangyu\|lua"
│
├─ 是否有 Lua 语法错误?
│  ├─ Yes → 修复 defense.lua,reload
│  └─ No → 继续
│
├─ 是否有 "module not found"?
│  ├─ Yes → 安装缺失模块,restart
│  └─ No → 继续
│
├─ 配置变量是否为空?
│  ├─ Yes → 检查 set $fangyu_* 位置
│  └─ No → 继续
│
├─ Gateway 是否可达?
│  ├─ No → 检查网络/防火墙,或设置 fail_mode=open
│  └─ Yes → 继续
│
└─ 签名是否正确?
   └─ 运行签名测试脚本对比
```

## 附录 C: 联系支持

如问题持续,请提供:
1. `openresty -V` 完整输出
2. 错误日志最近 50 行
3. nginx.conf 中 Fangyu 相关配置
4. `curl -v http://your-site/` 完整输出

# OpenResty / Nginx-Lua 快速排查手册

## 问题：在 1Panel 中部署 defense.lua 不生效

### 快速诊断（5 分钟）

```bash
# 1. 检查 Lua 脚本是否存在
ls -la /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua

# 2. 检查配置语法
openresty -t

# 3. 查看最近的错误日志
tail -n 50 /opt/1panel/apps/openresty/openresty/logs/error.log | grep -iE "lua|fangyu"

# 4. 测试请求并检查响应
curl -v http://localhost/ 2>&1 | grep -i "x-"
curl -s http://localhost/ | grep -o "window.__fy_server_ctx"

# 5. 检查进程是否运行
ps aux | grep openresty
```

---

## 常见问题速查表

| 现象 | 可能原因 | 快速修复 |
|------|---------|---------|
| `module 'resty.hmac' not found` | 缺少 HMAC 模块 | 安装 lua-resty-openssl 或 lua-resty-hmac |
| `attempt to call field 'new' (a nil value)` | HMAC 模块 API 不匹配 | 检查 defense.lua 第 49-60 行的模块检测逻辑 |
| HTML 中无 SDK 脚本 | 未配置 body_filter 或非 HTML 响应 | 检查 nginx.conf 的 body_filter_by_lua_block |
| Gateway 返回 401 | 签名错误或密钥不匹配 | 运行 `python tests/adapters/test_lua_signature.py` |
| 配置变量为空 | `set $fangyu_*` 作用域错误 | 必须在 server{} 或 location{} 块内 |
| 所有请求都被拦截 | fail_mode=closed 且 Gateway 不可达 | 改为 fail_mode=open 或检查网络 |
| 日志无任何 Fangyu 输出 | Lua 脚本未被调用 | 检查 access_by_lua_file 路径是否正确 |
| `lua_code_cache is off` 警告 | 开发模式，性能极差 | 改为 `lua_code_cache on;` |

---

## 1Panel 专属注意事项

### 文件路径

```bash
# OpenResty 根目录（1Panel 默认）
/opt/1panel/apps/openresty/openresty/

# Lua 脚本推荐位置
/opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua

# 站点配置文件（通过 1Panel 界面编辑）
/opt/1panel/apps/openresty/openresty/www/sites/<your-site>/conf/nginx.conf

# 错误日志
/opt/1panel/apps/openresty/openresty/logs/error.log
/opt/1panel/apps/openresty/openresty/www/sites/<your-site>/logs/error.log
```

### 在 1Panel 界面配置

1. 登录 1Panel 管理后台
2. 进入 **网站** → 选择你的站点 → **配置**
3. 找到 `server {}` 块
4. 在 `location /` **之前** 添加变量定义：

```nginx
server {
    # ... listen, server_name 等

    # ★ 在这里添加 Fangyu 变量
    set $fangyu_gateway_url  "https://your-gateway.com";
    set $fangyu_site_id      "site_xxxxxxxx";
    set $fangyu_app_id       "12345";  # 必须是数字
    set $fangyu_app_secret   "your_secret";
    set $fangyu_fail_mode    "open";
    set $fangyu_sdk_inject   "on";
    set $fangyu_sdk_url      "";
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";

    location / {
        # ★ 添加这一行
        access_by_lua_file /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua;

        # 你的原有配置...
        root /path/to/web;
        index index.html;

        # ★ 添加 SDK 注入
        body_filter_by_lua_block {
            local snippet = ngx.ctx.fy_sdk_snippet
            if not snippet then return end
            local ct = ngx.header["Content-Type"] or ""
            if not ct:find("text/html", 1, true) then return end
            local chunk = ngx.arg[1]
            if chunk then
                ngx.arg[1] = chunk:gsub("</head>", snippet .. "</head>", 1)
            end
        }
    }
}
```

5. 点击 **保存** → **重启站点**

---

## 安装缺失的 Lua 模块

### 方法一：安装 lua-resty-openssl（推荐）

```bash
cd /tmp
git clone https://github.com/fffonion/lua-resty-openssl.git
cd lua-resty-openssl
make install LUA_LIB_DIR=/opt/1panel/apps/openresty/openresty/lualib
```

### 方法二：安装 lua-resty-hmac（兼容老版本）

```bash
cd /tmp
git clone https://github.com/jkeys089/lua-resty-hmac.git
cp -r lua-resty-hmac/lib/resty/* /opt/1panel/apps/openresty/openresty/lualib/resty/
```

### 验证安装

```bash
find /opt/1panel/apps/openresty/openresty/lualib -name "hmac.lua"
# 应该看到类似输出：
# /opt/1panel/apps/openresty/openresty/lualib/resty/hmac.lua
# 或
# /opt/1panel/apps/openresty/openresty/lualib/resty/openssl/hmac.lua
```

---

## 调试技巧

### 1. 启用详细日志

在 `defense.lua` 开头添加：

```lua
ngx.log(ngx.ERR, "[fangyu] Script loaded, version: 2024-08-07")
```

在第 83 行后添加：

```lua
ngx.log(ngx.ERR, "[fangyu] Config: GATEWAY_URL=", GATEWAY_URL, 
        " SITE_ID=", SITE_ID, " APP_ID=", APP_ID)
```

在第 431 行后添加：

```lua
ngx.log(ngx.ERR, "[fangyu] Decision: mechanism=", 
        payload and payload.mechanism or "nil", " verdict=", 
        payload and payload.verdict or "nil")
```

### 2. 实时监控日志

```bash
# 终端 1：访问日志
tail -f /opt/1panel/apps/openresty/openresty/logs/access.log

# 终端 2：错误日志（筛选 Fangyu）
tail -f /opt/1panel/apps/openresty/openresty/logs/error.log | grep --line-buffered fangyu

# 终端 3：发送测试请求
while true; do curl -s http://localhost/ > /dev/null; sleep 2; done
```

### 3. 检查变量是否传递

在 `location /` 块内添加临时调试：

```nginx
location / {
    access_by_lua_block {
        ngx.log(ngx.ERR, "[debug] fangyu_gateway_url=", ngx.var.fangyu_gateway_url)
        ngx.log(ngx.ERR, "[debug] fangyu_site_id=", ngx.var.fangyu_site_id)
        ngx.log(ngx.ERR, "[debug] fangyu_app_secret=", 
                ngx.var.fangyu_app_secret and "***SET***" or "EMPTY")
    }
    
    access_by_lua_file /path/to/defense.lua;
    # ...
}
```

重载后查看日志，确认变量不为空。

### 4. 最小化测试配置

创建一个最简单的测试配置，排除其他干扰：

```nginx
server {
    listen 8888;
    server_name _;
    
    set $fangyu_gateway_url  "";  # 故意留空，触发 not_configured
    set $fangyu_site_id      "";
    set $fangyu_app_secret   "";
    set $fangyu_fail_mode    "open";
    
    location / {
        access_by_lua_file /opt/1panel/apps/openresty/openresty/conf/lua/fangyu/defense.lua;
        return 200 "Test OK\n";
    }
}
```

如果这个配置都不工作，说明是脚本本身的问题。

---

## 使用自动化测试脚本

我们已经为你准备了自动化测试脚本，运行一次即可诊断大部分问题：

```bash
# 1. 上传测试脚本到服务器
scp tests/adapters/test_openresty_deployment.sh user@server:/tmp/

# 2. SSH 登录服务器
ssh user@server

# 3. 设置权限
chmod +x /tmp/test_openresty_deployment.sh

# 4. 运行测试（需要 root 或 sudo）
sudo /tmp/test_openresty_deployment.sh

# 5. 可选：指定自定义路径
sudo TEST_URL=http://your-domain.com \
     OPENRESTY_PREFIX=/opt/1panel/apps/openresty/openresty \
     /tmp/test_openresty_deployment.sh
```

测试脚本会自动检查：
- ✓ OpenResty 版本和依赖
- ✓ Lua 脚本文件和权限
- ✓ Nginx 配置语法
- ✓ 必需的 Lua 模块
- ✓ 进程运行状态
- ✓ 错误日志分析
- ✓ HTTP 请求测试
- ✓ SDK 注入验证
- ✓ Gateway 连通性
- ✓ 签名算法一致性

---

## 验证部署成功

### 最终检查清单

运行以下命令，所有输出都应该符合预期：

```bash
# 1. 配置语法正确
openresty -t
# 期望: nginx: configuration file ... test is successful

# 2. 无 Lua 错误
tail -n 100 /opt/1panel/apps/openresty/openresty/logs/error.log | grep -i "lua error"
# 期望: 无输出

# 3. HTTP 请求成功
curl -I http://localhost/
# 期望: HTTP/1.1 200 OK

# 4. SDK 已注入
curl -s http://localhost/ | grep "window.__fy_server_ctx"
# 期望: 看到包含 SDK 上下文的 <script> 标签

# 5. 配置变量非空（在日志中查找你添加的调试输出）
grep "fangyu.*Config:" /opt/1panel/apps/openresty/openresty/logs/error.log | tail -1
# 期望: 看到非空的 GATEWAY_URL, SITE_ID 等
```

### 功能测试

```bash
# 模拟正常访问
curl -A "Mozilla/5.0" -H "X-Forwarded-For: 1.1.1.1" http://localhost/

# 模拟可疑访问（如果你配置了相应规则）
curl -A "python-requests" -H "X-Forwarded-For: 1.1.1.1" http://localhost/

# 查看决策日志
tail -n 20 /opt/1panel/apps/openresty/openresty/logs/error.log | grep "fangyu.*Decision"
```

---

## 性能优化建议

部署成功后，建议进行以下优化：

1. **开启 Lua 代码缓存**（必须）

```nginx
http {
    lua_code_cache on;  # 生产环境必须开启
}
```

2. **缓存 Gateway 决策结果**（可选）

```nginx
http {
    lua_shared_dict fangyu_cache 10m;
}
```

在 `defense.lua` 中添加缓存逻辑（第 430 行之前）：

```lua
local cache = ngx.shared.fangyu_cache
local cache_key = "dec:" .. real_ip
local cached = cache:get(cache_key)
if cached then
    local payload = cjson.decode(cached)
    if payload then
        execute(payload)
        return
    end
end

-- ... 原有的 decide() 调用

if payload then
    cache:set(cache_key, cjson.encode(payload), 300)  -- 缓存 5 分钟
end
```

3. **静态资源跳过检查**

```nginx
location ~* \.(js|css|png|jpg|gif|ico|svg)$ {
    # 不调用 access_by_lua_file，直接放行
    root /path/to/web;
    expires 7d;
}
```

4. **限流保护**

```nginx
http {
    limit_req_zone $binary_remote_addr zone=fangyu:10m rate=20r/s;
}

server {
    location / {
        limit_req zone=fangyu burst=50 nodelay;
        access_by_lua_file ...;
    }
}
```

---

## 回滚方案

如果部署出现问题，需要快速回滚：

### 方案 1：禁用 Lua 脚本

注释掉 `access_by_lua_file` 行：

```nginx
location / {
    # access_by_lua_file /path/to/defense.lua;  # 已禁用
    root /path/to/web;
}
```

### 方案 2：强制放行模式

```nginx
set $fangyu_fail_mode    "open";
set $fangyu_gateway_url  "";  # 空 URL 会触发 not_configured，直接放行
```

### 方案 3：使用备份配置

```bash
# 回滚配置文件
cp /opt/1panel/apps/openresty/openresty/conf/nginx.conf.backup \
   /opt/1panel/apps/openresty/openresty/conf/nginx.conf

# 重启
systemctl restart openresty
```

---

## 获取帮助

如果问题仍未解决，请收集以下信息：

```bash
# 生成诊断报告
cat > /tmp/fangyu_diag.txt << EOF
=== OpenResty 版本 ===
$(openresty -V 2>&1)

=== Lua 模块列表 ===
$(find /opt/1panel/apps/openresty/openresty/lualib -name "*.lua" -o -name "*.so" | head -20)

=== 配置语法检查 ===
$(openresty -t 2>&1)

=== 最近错误日志 ===
$(tail -n 50 /opt/1panel/apps/openresty/openresty/logs/error.log)

=== Nginx 配置片段 ===
$(grep -A 10 -B 2 "fangyu" /opt/1panel/apps/openresty/openresty/conf/nginx.conf 2>/dev/null || echo "未找到")

=== 测试请求 ===
$(curl -v http://localhost/ 2>&1 | head -30)
EOF

echo "诊断报告已生成: /tmp/fangyu_diag.txt"
```

然后将 `/tmp/fangyu_diag.txt` 发送给技术支持。

---

## 参考文档

- 完整部署指南: `docs/deployment/OPENRESTY_DEPLOYMENT.md`
- 配置示例: `adapters/nginx-lua/examples/1panel-full-config.conf`
- 自动化测试: `tests/adapters/test_openresty_deployment.sh`
- 签名验证: `tests/adapters/test_lua_signature.py`

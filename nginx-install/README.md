# Nginx + Lua 部署工具集

这个目录包含 Fangyu Defense System 的 Nginx + OpenResty Lua 部署和诊断工具。

---

## 📁 目录结构

```
nginx-dep/
├── README.md                        # 本文件
├── nginx-lua-manual-setup.md        # 手动配置指南（核心文档）
├── diagnose_sdk_injection.py        # SDK 注入诊断工具
├── fix_nginx_conf.py               # nginx.conf 修复工具
├── apply_nginx_fix.py              # 自动应用修复
├── test_sdk_injection.py           # SDK 注入测试
└── quick_test_lua.py               # Lua 模块快速测试
```

---

## 🚀 快速开始

### 场景 1：首次部署新站点

```bash
# 1. 运行完整部署脚本（自动检测并提示 nginx.conf 问题）
python fangyu_scripts.py

# 2. 诊断配置
cd nginx-dep
python diagnose_sdk_injection.py

# 3. 如果提示 nginx.conf 缺少 Lua 配置，自动修复
python fix_nginx_conf.py
python apply_nginx_fix.py

# 4. 验证修复
python diagnose_sdk_injection.py

# 5. 测试 SDK 注入
python test_sdk_injection.py
```

### 场景 2：SDK 不注入排查

```bash
cd nginx-dep

# 1. 运行诊断（8 项检查）
python diagnose_sdk_injection.py

# 2. 根据诊断结果修复问题
# - 如果是 nginx.conf 问题 → 运行 fix_nginx_conf.py
# - 如果是配置问题 → 重新运行 fangyu_scripts.py
# - 如果配置都正常但 SDK 不注入 → 查看文档排查其他原因

# 3. 验证修复
python test_sdk_injection.py
```

### 场景 3：手动配置（无 1Panel API）

如果无法使用自动化脚本（例如网络隔离、权限限制），参考：

📖 **[nginx-lua-manual-setup.md](./nginx-lua-manual-setup.md)** - 完整手动配置指南

---

## 🔧 工具说明

### 1. diagnose_sdk_injection.py

**功能**：诊断 SDK 不注入的根本原因

**检查项**：
- ✓ nginx.conf 中的 Lua 模块配置（**最关键**）
- ✓ $fy_sdk_snippet 变量声明
- ✓ body_filter_by_lua_block 配置
- ✓ access_by_lua_file 配置
- ✓ SDK 注入开关
- ✓ fail_mode 配置
- ✓ 网关配置（URL、Site ID、App ID、Secret）
- ✓ defense.lua 文件存在性

**用法**：
```bash
python diagnose_sdk_injection.py
```

**输出**：
- 🚨 CRITICAL 问题：必须修复才能工作
- ⚠️ HIGH 问题：高优先级，影响功能
- 📋 WARNING：建议优化，不影响核心功能

---

### 2. fix_nginx_conf.py

**功能**：生成修复后的 nginx.conf

**修复内容**：
在 `http` 块中添加：
```nginx
lua_package_path "/usr/local/openresty/lualib/?.lua;/usr/local/openresty/site/lualib/?.lua;;";
lua_package_cpath "/usr/local/openresty/lualib/?.so;/usr/local/openresty/site/lualib/?.so;;";
lua_code_cache on;
```

**用法**：
```bash
python fix_nginx_conf.py
```

**输出**：
- 生成 `nginx.conf.fixed` 并上传到容器
- 显示手动应用步骤

---

### 3. apply_nginx_fix.py

**功能**：自动应用 nginx.conf 修复（通过 1Panel API）

**步骤**：
1. 备份原 nginx.conf
2. 测试新配置（nginx -t）
3. 应用新配置
4. 重载 Nginx

**用法**：
```bash
python apply_nginx_fix.py
```

**前提**：
- 已运行 `fix_nginx_conf.py`
- 容器中存在 `/usr/local/openresty/nginx/conf/nginx.conf.fixed`

---

### 4. test_sdk_injection.py

**功能**：测试 SDK 是否成功注入

**检查内容**：
- 访问网站首页
- 检查 HTML 中是否包含 SDK script 标签
- 验证 SDK URL 格式

**用法**：
```bash
python test_sdk_injection.py
```

**输出**：
- ✓ SDK 已注入（显示注入位置）
- ✗ SDK 未注入（建议运行诊断脚本）

---

### 5. quick_test_lua.py

**功能**：快速测试 Lua 模块是否工作

**原理**：
1. 创建最简单的 test_simple.lua（只有一行日志）
2. 替换 defense.lua
3. 发送测试请求
4. 检查 Nginx 错误日志

**用法**：
```bash
python quick_test_lua.py
```

**用途**：
- 快速验证 Lua 模块是否启用
- 排除复杂 Lua 代码的干扰
- 确认是配置问题还是代码问题

---

## 📖 文档

### nginx-lua-manual-setup.md

**完整手动配置指南**，包含：

- ✅ 问题诊断步骤
- ✅ 自动修复方法（推荐）
- ✅ 完全手动修复步骤
- ✅ 配置验证方法
- ✅ 常见问题解答
- ✅ 技术细节说明

**适用场景**：
- 无法使用自动化脚本
- 需要深入了解配置原理
- 遇到特殊情况需要手动调整

---

## 🔍 故障排查流程

```
SDK 不注入
    ↓
运行 diagnose_sdk_injection.py
    ↓
├─ nginx.conf 缺少 Lua 配置
│   ↓
│   fix_nginx_conf.py → apply_nginx_fix.py
│   ↓
│   验证：diagnose_sdk_injection.py
│
├─ 其他配置问题
│   ↓
│   重新运行 fangyu_scripts.py
│   ↓
│   验证：diagnose_sdk_injection.py
│
└─ 配置全部正常但 SDK 不注入
    ↓
    quick_test_lua.py（测试 Lua 是否工作）
    ↓
    ├─ Lua 不工作 → 检查 nginx.conf
    └─ Lua 工作 → 检查 defense.lua 逻辑
```

---

## 🎯 常见问题

### Q1：为什么需要修复 nginx.conf？

**A**：1Panel 创建的 OpenResty 容器默认不包含 Lua 模块配置，导致：
- ❌ `access_by_lua_file` 不执行
- ❌ `body_filter_by_lua_block` 不执行
- ❌ 所有 Lua 代码失效

### Q2：修复一次还是每个站点都要修复？

**A**：**只需修复一次**！
- ✅ nginx.conf 是全局配置
- ✅ 所有站点共享
- ✅ 修复后所有站点立即生效
- ✅ 以后新建站点自动支持 Lua

### Q3：自动修复失败怎么办？

**A**：使用手动修复：
1. 阅读 [nginx-lua-manual-setup.md](./nginx-lua-manual-setup.md)
2. 通过 1Panel 界面进入容器终端
3. 按文档步骤手动编辑 nginx.conf

### Q4：如何确认修复成功？

**A**：运行诊断脚本，看到以下结果即为成功：

```
✓ nginx.conf 中已配置 Lua 模块
✓ $fy_sdk_snippet 已声明
✓ body_filter_by_lua_block 配置正确
✓ access_by_lua_file 已配置
✓ SDK 注入开关正常
✓ fail_mode 配置正常
✓ 网关配置完整
✓ defense.lua 文件正常

✅ 配置检查通过！未发现严重问题
```

---

## 📦 依赖

所有脚本依赖主目录的 `fangyu_scripts.py`：

```python
from fangyu_scripts import (
    OnePanelAPIClient,
    ContainerManager,
    Logger,
    Colors
)
```

**配置位置**：
- 1Panel URL 和 API Key：在各脚本的 `main()` 函数中
- 域名：在各脚本的 `DOMAIN` 变量中

---

## 🔗 相关文件

| 文件路径 | 说明 |
|---------|------|
| `../fangyu_scripts.py` | 主部署脚本（包含自动检测 nginx.conf） |
| `../adapters/nginx-lua/defense.lua` | Lua 防御代码 |
| `../docs/` | 其他文档 |

---

## 📝 更新历史

| 日期 | 更新内容 |
|------|----------|
| 2026-08-07 | 创建 nginx-dep 工具集 |
| 2026-08-07 | 添加 nginx.conf 自动检测和修复功能 |
| 2026-08-07 | 创建完整文档 |

---

## 📞 支持

遇到问题？

1. 📖 查看 [nginx-lua-manual-setup.md](./nginx-lua-manual-setup.md)
2. 🔍 运行 `diagnose_sdk_injection.py` 获取详细诊断
3. 🐛 检查 Nginx 错误日志：`/usr/local/openresty/nginx/logs/error.log`



```bash
server {
    listen 80; 
    listen 443 ssl; 
    server_name wayaffair.shop; 

    # ==================== 0. DNS 解析器配置（解决此报错的核心） ====================
    # 指定 DNS 解析服务器（公共 DNS 1.1.1.1 / 8.8.8.8 或阿里云 DNS 223.5.5.5）
    resolver 1.1.1.1 8.8.8.8 223.5.5.5 ipv6=off valid=30s;

    # ==================== 1. Fangyu Defense 防御脚本变量配置 ====================
    set $fangyu_gateway_url   "https://gateway.foxfingerlab.com";
    set $fangyu_site_id       "site_eba8689a";
    set $fangyu_app_id        "1";
    set $fangyu_app_secret    "bd5f8a076002101ff410fd127dd5d5e71452c00e9aa479bf";
    set $fangyu_fail_mode     "open";
    set $fangyu_sdk_inject    "on";
    set $fangyu_blocked_url   "/blocked";
    set $fangyu_challenge_url "/challenge";
    set $fy_sdk_snippet      "";
    set $fy_server_token      "";

    # ... 后续其余配置保持不变 ...
    index index.php index.html index.htm; 
    
    # 基础路径与日志
    access_log /www/sites/wayaffair.shop/log/access.log main; 
    error_log /www/sites/wayaffair.shop/log/error.log; 

    # ==================== 2. SSL 证书与安全配置 ====================
    ssl_certificate /www/sites/wayaffair.shop/ssl/fullchain.pem; 
    ssl_certificate_key /www/sites/wayaffair.shop/ssl/privkey.pem; 
    ssl_protocols TLSv1.2 TLSv1.3; 
    ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256; 
    ssl_prefer_server_ciphers off; 
    ssl_session_cache shared:SSL:10m; 
    ssl_session_timeout 10m; 

    error_page 497 https://$host$request_uri; 
    add_header Strict-Transport-Security "max-age=31536000"; 

    # ==================== 3. 基础跳转与安全放行 ====================
    # HTTP 强制跳转 HTTPS
    if ($scheme = http) {
        return 301 https://$host$request_uri; 
    }

    # 屏蔽敏感文件
    location ~ ^/(\.user\.ini|\.htaccess|\.git|\.env|\.svn|\.project|LICENSE|README\.md) {
        return 404; 
    }
    
    # SSL 证书申请放行
    location ^~ /.well-known/acme-challenge {
        allow all; 
        root /usr/share/nginx/html; 
    }

    # 防止恶意调用敏感扩展文件
    if ($uri ~ "^/\.well-known/.*\.(php|jsp|py|js|css|lua|ts|go|zip|tar\.gz|rar|7z|sql|bak)$") {
        return 403; 
    }

    # ==================== 4. 核心反向代理与 Lua 注入逻辑 ====================
    location / {
        # A. 执行防御/网关通信 Lua 脚本
        access_by_lua_file /www/sites/wayaffair.shop/lua/defense.lua;

        # B. 关键点：剥离上游压缩头与去除 Accept-Encoding，确保 Lua 拿到解压后的明文 HTML
        proxy_set_header Accept-Encoding "";
        proxy_hide_header Content-Encoding;

        # C. 传递正确域名，避免 WordPress 产生 301 重定向死循环
        proxy_set_header Host $http_host; 
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; 
        proxy_set_header X-Real-IP $remote_addr; 
        proxy_set_header X-Forwarded-Proto $scheme; 
        proxy_set_header X-Forwarded-Host $server_name; 
        proxy_set_header Connection "upgrade"; 
        proxy_set_header Upgrade $http_upgrade; 

        proxy_http_version 1.1; 
        proxy_ssl_server_name off; 
        proxy_ssl_name $proxy_host; 

        # 反向代理上游 Apache/WordPress 端口
        proxy_pass http://127.0.0.1:8081; 

        # D. 安全替换注入 SDK 代码
        body_filter_by_lua_block {
            local snippet = ngx.var.fy_sdk_snippet
            if not snippet or snippet == "" then return end

            local ct = ngx.header["Content-Type"] or ""
            if type(ct) == "string" and string.find(ct, "text/html", 1, true) then
                local chunk = ngx.arg[1]
                if chunk and type(chunk) == "string" and chunk ~= "" then
                    -- 打印 Debug 日志，便于通过 error.log 确认注入触发情况
                    ngx.log(ngx.INFO, "[fangyu] 准备注入 SDK，当前片段长度: ", #snippet)

                    -- 转义 % 符号，防止字符串正则替换触发 500 异常
                    local safe_snippet = snippet:gsub("%%", "%%%%")
                    local new_chunk, count = string.gsub(chunk, "</head>", safe_snippet .. "</head>", 1)
                    if count > 0 then
                        ngx.arg[1] = new_chunk
                    end
                end
            end
        }
    }
}

```
# Fangyu Defense 手动部署指南

本指南适用于无法使用自动化脚本的情况，通过 1Panel 面板手动部署 Fangyu 防御系统。

---

## 📋 部署前准备

### 必需信息
- **站点域名**：`your-domain.com`
- **Fangyu 站点 ID**：`site_xxxxxxxx`
- **Fangyu 应用 ID**：`1`
- **Fangyu 应用密钥**：`your_app_secret`
- **Fangyu 网关 URL**：`https://gateway.example.com`

### 环境要求
- OpenResty / Nginx with Lua 支持
- 1Panel 管理面板
- 站点已创建并可正常访问

---

## 🔧 部署步骤

### 步骤 1：进入容器

1. 登录 1Panel 面板
2. 进入 **容器管理** → 找到 OpenResty 容器
3. 点击 **终端** 按钮，打开容器 Shell

或使用命令行：
```bash
# 查找容器 ID
docker ps | grep openresty

# 进入容器
docker exec -it <container_id> sh
```

---

### 步骤 2：创建目录结构

```bash
# 替换 your-domain.com 为实际域名
DOMAIN="your-domain.com"

# 创建 Lua 脚本目录
mkdir -p /www/sites/${DOMAIN}/lua

# 设置权限
chmod 755 /www/sites/${DOMAIN}/lua
```

---

### 步骤 3：上传 defense.lua 文件

#### 方法 A：通过 1Panel 文件管理器

1. 在 1Panel 面板，进入 **容器** → **文件管理**
2. 导航到 `/www/sites/your-domain.com/lua/`
3. 上传本地的 `defense.lua` 文件
   - 文件位置：`adapters/nginx-lua/defense.lua`
   - 文件大小应 >20KB

#### 方法 B：通过命令行复制

```bash
# 在宿主机执行（从项目根目录）
docker cp adapters/nginx-lua/defense.lua <container_id>:/www/sites/${DOMAIN}/lua/

# 进入容器验证
docker exec -it <container_id> ls -lh /www/sites/${DOMAIN}/lua/
```

#### 方法 C：通过 vi 编辑器创建

```bash
# 在容器内执行
vi /www/sites/${DOMAIN}/lua/defense.lua

# 粘贴 defense.lua 文件内容
# 保存：ESC → :wq
```

---

### 步骤 4：创建 Real-IP 配置文件

```bash
# 在容器内创建文件
cat > /www/sites/${DOMAIN}/lua/fangyu_real_ip.conf << 'EOF'
set_real_ip_from 127.0.0.1;
set_real_ip_from 10.0.0.0/8;
set_real_ip_from 172.16.0.0/12;
set_real_ip_from 192.168.0.0/16;
set_real_ip_from 100.64.0.0/10;
set_real_ip_from 169.254.0.0/16;
set_real_ip_from ::1;
set_real_ip_from 173.245.48.0/20;
set_real_ip_from 103.21.244.0/22;
set_real_ip_from 103.22.200.0/22;
set_real_ip_from 103.31.4.0/22;
set_real_ip_from 141.101.64.0/18;
set_real_ip_from 108.162.192.0/18;
set_real_ip_from 190.93.240.0/20;
set_real_ip_from 188.114.96.0/20;
set_real_ip_from 197.234.240.0/22;
set_real_ip_from 198.41.128.0/17;
set_real_ip_from 162.158.0.0/15;
set_real_ip_from 104.16.0.0/13;
set_real_ip_from 104.24.0.0/14;
set_real_ip_from 172.64.0.0/13;
set_real_ip_from 131.0.72.0/22;
set_real_ip_from 2400:cb00::/32;
set_real_ip_from 2606:4700::/32;
set_real_ip_from 2803:f800::/32;
set_real_ip_from 2405:b500::/32;
set_real_ip_from 2405:8100::/32;
set_real_ip_from 2a06:98c0::/29;
set_real_ip_from 2c0f:f248::/32;
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
EOF
```

---

### 步骤 5：修改站点 Nginx 配置

#### 5.1 找到配置文件

在 1Panel 中：
1. 进入 **网站管理**
2. 找到目标站点，点击 **配置**
3. 或直接编辑：`/usr/local/openresty/nginx/conf/conf.d/your-domain.com.conf`

#### 5.2 在 server 块中添加变量（server_name 之后）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # ========== Fangyu Defense 配置 ==========
    include /www/sites/your-domain.com/lua/fangyu_real_ip.conf;

    # Fangyu 变量配置
    set $fangyu_gateway_url  "https://gateway.example.com";
    set $fangyu_site_id      "site_xxxxxxxx";
    set $fangyu_app_id       "1";
    set $fangyu_app_secret   "your_app_secret";
    set $fangyu_fail_mode    "open";
    set $fangyu_sdk_inject   "on";
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";
    set $fy_sdk_snippet      "";
    set $fy_server_token     "";
    # ==========================================
    
    location / {
        # 其他配置...
    }
}
```

#### 5.3 在 location / 块的开头添加

```nginx
location / {
    # Fangyu 访问控制
    access_by_lua_file /www/sites/your-domain.com/lua/defense.lua;
    proxy_set_header Accept-Encoding "";
    proxy_hide_header Content-Encoding;
    
    # 原有配置
    proxy_pass http://upstream;
    # ...
}
```

#### 5.4 在 location / 块的结束前添加

```nginx
location / {
    # 前面的配置...
    
    # Fangyu SDK 注入
    body_filter_by_lua_block {
        local snippet = ngx.var.fy_sdk_snippet
        if not snippet or snippet == "" then return end

        local content_type = ngx.header["Content-Type"] or ""
        if type(content_type) == "string" and string.find(content_type, "text/html", 1, true) then
            local chunk = ngx.arg[1]
            if chunk and type(chunk) == "string" and chunk ~= "" then
                local safe_snippet = snippet:gsub("%%", "%%%%")
                local new_chunk, count = string.gsub(chunk, "</head>", safe_snippet .. "</head>", 1)
                if count > 0 then
                    ngx.arg[1] = new_chunk
                end
            end
        end
    }
}
```

---

### 步骤 6：配置 nginx.conf（可选但推荐）

#### 6.1 编辑主配置文件

```bash
vi /usr/local/openresty/nginx/conf/nginx.conf
```

#### 6.2 在 http 块开头添加

```nginx
http {
    # Lua 包路径配置
    lua_package_path "/usr/local/openresty/lualib/?.lua;;";
    lua_package_cpath "/usr/local/openresty/lualib/?.so;;";
    lua_code_cache on;
    
    # DNS resolver 配置（用于网关通信）
    resolver 8.8.8.8 8.8.4.4 ipv6=off;
    
    # 其他配置...
}
```

> **注意**：OpenResty 通常已包含 Lua 路径配置，如已存在则跳过此步骤。

---

### 步骤 7：验证配置语法

```bash
# 测试 Nginx 配置语法
nginx -t

# 预期输出：
# nginx: the configuration file /usr/local/openresty/nginx/conf/nginx.conf syntax is ok
# nginx: configuration file /usr/local/openresty/nginx/conf/nginx.conf test is successful
```

---

### 步骤 8：重载 Nginx

#### 通过 1Panel（推荐）
1. 在 1Panel 网站管理中点击 **保存** 按钮
2. 1Panel 会自动验证并重载配置

#### 通过命令行
```bash
# 方法 1：平滑重载
nginx -s reload

# 方法 2：重启容器（不推荐）
docker restart <container_id>
```

---

## ✅ 部署验证

### 验证 1：检查文件是否存在

```bash
# 验证 defense.lua
ls -lh /www/sites/your-domain.com/lua/defense.lua
# 预期：-rw-r--r-- 1 root root 21K

# 验证 Real-IP 配置
ls -lh /www/sites/your-domain.com/lua/fangyu_real_ip.conf
# 预期：-rw-r--r-- 1 root root 996
```

### 验证 2：检查配置是否生效

```bash
# 查看站点配置
cat /usr/local/openresty/nginx/conf/conf.d/your-domain.com.conf | grep fangyu

# 预期输出应包含：
# set $fangyu_gateway_url
# set $fangyu_site_id
# access_by_lua_file
# body_filter_by_lua_block
```

### 验证 3：查看 Nginx 日志

```bash
# 实时查看错误日志
tail -f /usr/local/openresty/nginx/logs/error.log | grep fangyu

# 访问网站后应看到类似：
# [fangyu-test] ========== defense.lua loaded ==========
```

### 验证 4：浏览器测试

1. 访问网站 `https://your-domain.com/`
2. 打开开发者工具 (F12)
3. **Network 标签**：查看响应头是否有 `X-Fangyu-*` 相关头
4. **Console 标签**：检查是否有 `window.fangyu` 对象
5. **Elements 标签**：查看 `<head>` 中是否注入了 Fangyu SDK 脚本

---

## 🔍 故障排查

### 问题 1：Nginx 重载失败

**症状**：`nginx -t` 报语法错误

**排查步骤**：
```bash
# 查看详细错误
nginx -t 2>&1

# 常见错误：
# - 路径错误：检查 /www/sites/域名/lua/ 路径是否正确
# - 括号不匹配：检查 body_filter_by_lua_block { } 是否闭合
# - 变量未定义：确认所有 $fangyu_* 变量都已声明
```

### 问题 2：defense.lua 未执行

**症状**：访问网站没有防御效果

**排查步骤**：
```bash
# 1. 确认文件存在
ls -la /www/sites/your-domain.com/lua/defense.lua

# 2. 查看错误日志
tail -100 /usr/local/openresty/nginx/logs/error.log

# 3. 测试 Lua 语法
luajit -bl /www/sites/your-domain.com/lua/defense.lua > /dev/null
```

### 问题 3：SDK 未注入

**症状**：网页源代码中没有 Fangyu SDK

**可能原因**：
1. `$fangyu_sdk_inject` 设置为 `"off"`
2. `body_filter_by_lua_block` 未正确配置
3. 响应不是 HTML 类型（Content-Type 不是 text/html）

**解决方法**：
```nginx
# 确认变量设置
set $fangyu_sdk_inject "on";  # 必须是 "on"

# 确认 body_filter 在正确的 location 块中
location / {
    # ...
    body_filter_by_lua_block { ... }  # 必须在 location / 内
}
```

### 问题 4：网关通信失败

**症状**：日志中显示 "connection refused" 或超时

**排查步骤**：
```bash
# 1. 测试网关连通性
curl -I https://gateway.example.com/api/health

# 2. 检查 DNS 解析
nslookup gateway.example.com

# 3. 检查容器网络
ping -c 3 gateway.example.com
```

---

## 📝 完整配置示例

### 站点配置文件完整示例

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL 证书配置
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # ========== Fangyu Defense 配置开始 ==========
    include /www/sites/your-domain.com/lua/fangyu_real_ip.conf;
    
    set $fangyu_gateway_url  "https://gateway.example.com";
    set $fangyu_site_id      "site_xxxxxxxx";
    set $fangyu_app_id       "1";
    set $fangyu_app_secret   "your_secret_here";
    set $fangyu_fail_mode    "open";
    set $fangyu_sdk_inject   "on";
    set $fangyu_blocked_url  "/blocked";
    set $fangyu_challenge_url "/challenge";
    set $fy_sdk_snippet      "";
    set $fy_server_token     "";
    # ========== Fangyu Defense 配置结束 ==========
    
    location / {
        # Fangyu 防御
        access_by_lua_file /www/sites/your-domain.com/lua/defense.lua;
        proxy_set_header Accept-Encoding "";
        proxy_hide_header Content-Encoding;
        
        # 反向代理配置
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SDK 注入
        body_filter_by_lua_block {
            local snippet = ngx.var.fy_sdk_snippet
            if not snippet or snippet == "" then return end
            
            local ct = ngx.header["Content-Type"] or ""
            if type(ct) == "string" and string.find(ct, "text/html", 1, true) then
                local chunk = ngx.arg[1]
                if chunk and type(chunk) == "string" and chunk ~= "" then
                    local safe_snippet = snippet:gsub("%%", "%%%%")
                    local new_chunk, count = string.gsub(chunk, "</head>", safe_snippet .. "</head>", 1)
                    if count > 0 then
                        ngx.arg[1] = new_chunk
                    end
                end
            end
        }
    }
    
    # 静态资源（可选）
    location /static/ {
        alias /www/sites/your-domain.com/static/;
    }
}
```

---

## 🔐 安全建议

1. **保护敏感信息**
   - 不要在日志中输出 `$fangyu_app_secret`
   - 使用环境变量或加密配置管理密钥

2. **文件权限**
   ```bash
   chmod 644 /www/sites/your-domain.com/lua/defense.lua
   chmod 644 /www/sites/your-domain.com/lua/fangyu_real_ip.conf
   ```

3. **定期更新**
   - 更新 defense.lua 到最新版本
   - 更新 Real-IP 配置（Cloudflare IP 段可能变化）

---

## 📚 相关文档

- [Fangyu Defense 开发文档](../README.md)
- [defense.lua 配置说明](../adapters/nginx-lua/README.md)
- [自动化部署脚本](./fangyu_template_migrator.py)
- [常见问题 FAQ](./faq.md)

---

## 💡 小贴士

### 快速重新部署
如需更新 defense.lua：
```bash
# 1. 备份旧文件
cp /www/sites/${DOMAIN}/lua/defense.lua /tmp/defense.lua.bak

# 2. 上传新文件
docker cp new-defense.lua <container_id>:/www/sites/${DOMAIN}/lua/defense.lua

# 3. 重载配置
nginx -s reload
```

### 批量部署多个站点
对于多个站点，只需重复步骤 2-5，为每个站点创建独立的目录和配置。

### 回滚操作
如需撤销部署：
```bash
# 1. 删除 Lua 文件
rm -rf /www/sites/${DOMAIN}/lua/

# 2. 编辑站点配置，删除所有 Fangyu 相关配置
vi /usr/local/openresty/nginx/conf/conf.d/${DOMAIN}.conf

# 3. 重载 Nginx
nginx -s reload
```

---

**部署完成！** 🎉

如有问题，请参考故障排查章节或联系技术支持。

# Nginx + OpenResty Lua 模块手动配置指南

## 问题背景

**症状**：部署 defense.lua 后，SDK 不注入，Lua 代码完全不执行

**根本原因**：nginx.conf 中缺少 Lua 模块配置，导致 OpenResty 的 Lua 功能未启用
# 在容器终端执行（复制粘贴）



## 诊断步骤

### 1. 运行诊断脚本

```bash
python diagnose_sdk_injection.py
```

如果看到以下错误：

```bash
✗ nginx.conf 中缺少 Lua 模块配置
  这是导致 Lua 代码完全不执行的根本原因！


则需要手动配置 nginx.conf。
```

---

## 自动修复（推荐）

### 方法 1：一键修复（完全自动化）

```bash
# 1. 生成修复后的配置文件
python fix_nginx_conf.py

# 2. 自动应用到容器（需要 1Panel API）
python apply_nginx_fix.py

# 3. 验证修复结果
python diagnose_sdk_injection.py
```

### 方法 2：生成 + 手动应用

```bash
# 1. 生成修复后的配置
python fix_nginx_conf.py
```

脚本会上传 `nginx.conf.fixed` 到容器的 `/usr/local/openresty/nginx/conf/` 目录。

然后通过 1Panel 界面或终端手动应用：

```bash
# 在容器终端执行
cd /usr/local/openresty/nginx/conf

# 备份原配置
cp nginx.conf nginx.conf.backup

# 测试新配置
nginx -t -c /usr/local/openresty/nginx/conf/nginx.conf.fixed

# 应用新配置
mv nginx.conf.fixed nginx.conf

# 重载 Nginx
nginx -s reload
```

---

## 手动修复（完全手动）

### 步骤 1：进入容器终端

通过 1Panel 界面：
1. 进入"容器"管理
2. 找到 OpenResty 容器（名称包含 `openresty`）
3. 点击"终端"按钮

### 步骤 2：备份原配置

```bash
cd /usr/local/openresty/nginx/conf
cp nginx.conf nginx.conf.backup.$(date +%Y%m%d_%H%M%S)
```

### 步骤 3：编辑 nginx.conf

```bash
vi nginx.conf
```

或者通过 1Panel 文件管理器打开编辑。

### 步骤 4：在 http 块中添加 Lua 配置

在 `http {` 块的**开头**（第一行之后）添加以下内容：

```nginx
http {
    # ============ Lua 模块配置（必需） ============
    # Lua 模块搜索路径
    lua_package_path "/usr/local/openresty/lualib/?.lua;/usr/local/openresty/site/lualib/?.lua;;";
    lua_package_cpath "/usr/local/openresty/lualib/?.so;/usr/local/openresty/site/lualib/?.so;;";
    
    # Lua 代码缓存（生产环境必须开启）
    lua_code_cache on;
    # ============================================
    
    # ... 其他原有配置 ...
}
```

**⚠️ 注意位置**：
- 必须在 `http {` 块内
- 必须在任何 `server {` 块之前
- 推荐放在 http 块的最开头

**完整示例**：

```nginx
user  nginx;
worker_processes  auto;

events {
    worker_connections  1024;
}

http {
    # ============ Lua 模块配置（必需） ============
    lua_package_path "/usr/local/openresty/lualib/?.lua;/usr/local/openresty/site/lualib/?.lua;;";
    lua_package_cpath "/usr/local/openresty/lualib/?.so;/usr/local/openresty/site/lualib/?.so;;";
    lua_code_cache on;
    # ============================================
    
    include       mime.types;
    default_type  application/octet-stream;
    
    sendfile        on;
    keepalive_timeout  65;
    
    # 引入站点配置
    include /usr/local/openresty/nginx/conf/conf.d/*.conf;
}
```

### 步骤 5：测试配置

```bash
nginx -t
```

应该看到：

```
nginx: the configuration file /usr/local/openresty/nginx/conf/nginx.conf syntax is ok
nginx: configuration file /usr/local/openresty/nginx/conf/nginx.conf test is successful
```

### 步骤 6：重载 Nginx

```bash
nginx -s reload
```

### 步骤 7：验证修复

退出容器终端，运行诊断脚本：

```bash
python diagnose_sdk_injection.py
```

应该看到：

```
✓ nginx.conf 中已配置 Lua 模块
```

---

## 验证 SDK 注入

修复后，运行完整测试：

```bash
# 1. 诊断配置（应该 8/8 全部通过）
python diagnose_sdk_injection.py

# 2. 测试 SDK 注入
python test_sdk_injection.py
```

预期结果：

```
✓ SDK 已注入！
  检测到 <script src="https://sdk.fangyu.com/v1/sdk.js"
```

---

## 常见问题

### Q1：为什么之前没有这个问题？

**A**：1Panel 创建的 OpenResty 容器默认不包含 Lua 配置。如果之前 SDK 能注入，可能是：
- 使用的是其他容器（已配置过）
- 使用的是旧版本 OpenResty（默认配置不同）

### Q2：修复会影响其他网站吗？

**A**：不会。nginx.conf 是全局配置，修复后：
- ✅ 所有网站共享同一个 Lua 配置
- ✅ 已部署 Fangyu 的网站立即生效
- ✅ 未部署 Fangyu 的网站不受影响
- ✅ 以后新建网站自动支持 Lua

### Q3：lua_code_cache 是什么？

**A**：控制 Lua 代码缓存：
- `on`（推荐）：缓存 Lua 代码，高性能，适合生产环境
- `off`：不缓存，每次请求重新加载，适合开发调试

### Q4：能否在站点配置中添加 Lua 配置？

**A**：不能。`lua_package_path` 和 `lua_package_cpath` 只能在 `http` 块中配置，不能在 `server` 或 `location` 块中。

### Q5：如何确认 Lua 模块是否工作？

**A**：运行最简单的测试：

```bash
python quick_test_lua.py
```

该脚本会：
1. 部署最简单的 test_simple.lua（只有一行日志）
2. 发送测试请求
3. 检查 Nginx 错误日志中是否有 `[TEST]` 标记

如果看到：
- ✓ Lua 模块工作正常
- ✗ Lua 模块不工作，检查 nginx.conf

---

## 技术细节

### Lua 模块路径说明

```nginx
lua_package_path "/usr/local/openresty/lualib/?.lua;/usr/local/openresty/site/lualib/?.lua;;";
```

- `/usr/local/openresty/lualib/?.lua`：OpenResty 内置 Lua 库
- `/usr/local/openresty/site/lualib/?.lua`：自定义 Lua 库
- `;;`：搜索默认路径

### 为什么需要 lua_code_cache？

生产环境必须开启：
- ✅ 高性能：避免重复编译 Lua 代码
- ✅ 支持 ngx.timer：定时器功能依赖代码缓存
- ✅ 支持 lua_shared_dict：共享内存字典需要缓存

关闭后的影响：
- ❌ 性能下降 10-100 倍
- ❌ 某些 Lua 功能不可用
- ⚠️ 仅用于开发调试

---

## 相关脚本

| 脚本 | 功能 |
|------|------|
| `fangyu_scripts.py` | 完整部署（包含自动检测 nginx.conf） |
| `diagnose_sdk_injection.py` | 诊断 SDK 不注入问题（8 项检查） |
| `fix_nginx_conf.py` | 生成修复后的 nginx.conf |
| `apply_nginx_fix.py` | 自动应用修复（通过 1Panel API） |
| `test_sdk_injection.py` | 测试 SDK 是否注入 |
| `quick_test_lua.py` | 快速测试 Lua 模块是否工作 |

---

## 修复历史

| 日期 | 修复内容 |
|------|----------|
| 2026-08-07 | 添加 nginx.conf 自动检测和修复功能 |
| 2026-08-07 | 创建本文档 |

---

## 参考资料

- [OpenResty 官方文档](https://openresty.org/en/lua-nginx-module.html)
- [lua_package_path 指令](https://github.com/openresty/lua-nginx-module#lua_package_path)
- [lua_code_cache 指令](https://github.com/openresty/lua-nginx-module#lua_code_cache)

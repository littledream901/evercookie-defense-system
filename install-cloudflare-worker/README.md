# Cloudflare Worker 自动部署工具

自动化部署 Fangyu Defense Worker 到 Cloudflare 的 Python 脚本。

---

## 📋 功能特性

- ✅ **Worker 脚本上传** - 自动上传并验证 JavaScript 代码
- ✅ **环境变量配置** - 自动配置 Fangyu 所需的所有环境变量
- ✅ **路由规则配置** - 可选配置自定义域名路由
- ✅ **幂等部署** - 重复执行会更新而非报错
- ✅ **详细日志** - 彩色输出，清晰的步骤提示
- ✅ **错误处理** - 完善的异常处理和回滚机制

---

## 🔧 前置准备

### 1. 安装依赖

```bash
pip install requests
```

### 2. 获取 Cloudflare 凭证

#### A. API Token（推荐）
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **My Profile** → **API Tokens**
3. 点击 **Create Token**
4. 选择模板 **Edit Cloudflare Workers**
5. 配置权限：
   - **Account** → **Workers Scripts** → **Edit**
   - **Zone** → **Workers Routes** → **Edit**（如果需要配置路由）
6. 复制生成的 Token

#### B. Account ID
1. 在 Cloudflare Dashboard 主页
2. 选择任意域名
3. 右侧栏查看 **Account ID**

#### C. Zone ID（可选，用于配置路由）
1. 选择目标域名
2. 右侧栏查看 **Zone ID**

---

## 🚀 使用方法

### 基本部署（不绑定路由）

```bash
python cloudflare_worker_deployer.py \
  --api-token "YOUR_CF_API_TOKEN" \
  --account-id "YOUR_ACCOUNT_ID" \
  --script-name "fangyu-defense" \
  --script-path "../adapters/shopify/cloudflare_worker/worker.js" \
  --gateway-url "https://gateway.foxfingerlab.com" \
  --site-id "site_eba8689a" \
  --app-id "1" \
  --app-secret "bd5f8a076002101ff410fd127dd5d5e71452c00e9aa479bf"
```

### 完整部署（包含路由）

```bash
python cloudflare_worker_deployer.py \
  --api-token "YOUR_CF_API_TOKEN" \
  --account-id "YOUR_ACCOUNT_ID" \
  --script-name "fangyu-defense" \
  --script-path "../adapters/shopify/cloudflare_worker/worker.js" \
  --gateway-url "https://gateway.foxfingerlab.com" \
  --site-id "site_eba8689a" \
  --app-id "1" \
  --app-secret "bd5f8a076002101ff410fd127dd5d5e71452c00e9aa479bf" \
  --zone-id "YOUR_ZONE_ID" \
  --route-pattern "example.com/*"
```

### 使用环境变量

```bash
# 设置环境变量
export CF_API_TOKEN="your_token_here"
export CF_ACCOUNT_ID="your_account_id"
export CF_ZONE_ID="your_zone_id"

# 运行脚本
python cloudflare_worker_deployer.py \
  --api-token "$CF_API_TOKEN" \
  --account-id "$CF_ACCOUNT_ID" \
  --script-name "fangyu-defense" \
  --script-path "../adapters/shopify/cloudflare_worker/worker.js" \
  --gateway-url "https://gateway.foxfingerlab.com" \
  --site-id "site_eba8689a" \
  --app-id "1" \
  --app-secret "your_secret" \
  --zone-id "$CF_ZONE_ID" \
  --route-pattern "*.example.com/*"
```

---

## 📝 参数说明

### 必需参数

| 参数 | 说明 | 示例 |
|-----|------|------|
| `--api-token` | Cloudflare API Token | `abc123...` |
| `--account-id` | Cloudflare Account ID | `1234567890abcdef` |
| `--script-name` | Worker 名称 | `fangyu-defense` |
| `--script-path` | Worker 脚本路径 | `./worker.js` |
| `--gateway-url` | Fangyu 网关 URL | `https://gateway.example.com` |
| `--site-id` | Fangyu 站点 ID | `site_xxxxxxxx` |
| `--app-id` | Fangyu 应用 ID | `1` |
| `--app-secret` | Fangyu 应用密钥 | `bd5f8a07...` |

### 可选参数

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `--zone-id` | Cloudflare Zone ID | 无（不配置路由） |
| `--route-pattern` | 路由模式 | 无（不配置路由） |
| `--fail-mode` | 失败模式（open/closed） | `open` |
| `--no-sdk-inject` | 禁用 SDK 注入 | 不禁用 |

---

## 🎯 路由模式示例

| 模式 | 匹配范围 | 用途 |
|-----|---------|------|
| `example.com/*` | 主域名所有路径 | 仅保护主站 |
| `*.example.com/*` | 所有子域名 | 保护所有子域 |
| `shop.example.com/*` | 特定子域名 | 仅保护商店 |
| `example.com/admin*` | 特定路径 | 仅保护后台 |

---

## 📊 部署流程

```
1. 读取 Worker 脚本
   └─ 验证脚本语法（检查 export default 和 async fetch）

2. 检查 Worker 是否已存在
   ├─ 已存在 → 更新
   └─ 不存在 → 创建

3. 上传 Worker 脚本
   └─ 使用 Cloudflare Workers API

4. 配置环境变量
   ├─ FANGYU_GATEWAY_URL
   ├─ FANGYU_SITE_KEY
   ├─ FANGYU_SITE_SECRET
   ├─ FANGYU_FAIL_MODE
   └─ FANGYU_SDK_INJECT

5. 配置路由（可选）
   ├─ 检查现有路由
   ├─ 删除冲突路由
   └─ 添加新路由

6. 部署完成
   └─ 打印后续步骤
```

---

## ✅ 部署验证

### 1. 查看 Worker 列表

```bash
curl -X GET "https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT_ID/workers/scripts" \
  -H "Authorization: Bearer YOUR_API_TOKEN" | jq .
```

### 2. 测试 Worker

```bash
# 访问你的网站
curl -I https://example.com/

# 检查响应头
# 应该能看到 Worker 处理的标记
```

### 3. 查看 Worker 日志

```bash
# 使用 wrangler CLI
wrangler tail fangyu-defense
```

### 4. 浏览器测试

1. 访问你的网站
2. 打开开发者工具 (F12)
3. **Network 标签**：查看请求
4. **Console 标签**：检查 `window.__fy_server_ctx`
5. **Elements 标签**：查看 `<head>` 中的 SDK 脚本

---

## 🔍 故障排查

### 问题 1：API Token 权限不足

**错误：**
```
API 调用失败: 10000: Authentication error
```

**解决方法：**
1. 确认 Token 有 **Workers Scripts:Edit** 权限
2. 如果配置路由，还需要 **Workers Routes:Edit** 权限
3. 重新生成 Token

### 问题 2：脚本上传失败

**错误：**
```
脚本上传失败: Worker script is invalid
```

**解决方法：**
1. 检查 worker.js 语法
2. 确认包含 `export default { async fetch(...) {...} }`
3. 本地测试：`node worker.js`（需要 Node.js）

### 问题 3：路由配置失败

**错误：**
```
路由配置失败: Zone not found
```

**解决方法：**
1. 确认 Zone ID 正确
2. 确认 Token 有该 Zone 的权限
3. 检查路由模式格式

### 问题 4：Worker 不生效

**可能原因：**
1. 路由未配置或配置错误
2. DNS 未解析到 Cloudflare
3. Worker 被其他规则覆盖

**解决方法：**
1. 检查 Cloudflare Dashboard → Workers → Routes
2. 确认域名 DNS 指向 Cloudflare（橙色云朵）
3. 调整路由优先级

---

## 🔄 更新 Worker

重新运行脚本即可更新：

```bash
python cloudflare_worker_deployer.py \
  --api-token "YOUR_CF_API_TOKEN" \
  --account-id "YOUR_ACCOUNT_ID" \
  --script-name "fangyu-defense" \
  --script-path "../adapters/shopify/cloudflare_worker/worker.js" \
  --gateway-url "https://gateway.foxfingerlab.com" \
  --site-id "site_eba8689a" \
  --app-id "1" \
  --app-secret "new_secret_here"
```

脚本会自动检测并更新现有 Worker。

---

## 🗑️ 删除 Worker

```bash
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT_ID/workers/scripts/fangyu-defense" \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

---

## 📚 相关文档

- [Cloudflare Workers 文档](https://developers.cloudflare.com/workers/)
- [Cloudflare API 文档](https://developers.cloudflare.com/api/)
- [Fangyu Defense 文档](../../README.md)
- [worker.js 说明](../adapters/shopify/cloudflare_worker/worker.js)

---

## 💡 最佳实践

1. **使用专用 API Token** - 为每个项目创建独立的 Token
2. **设置环境变量** - 不要在命令行中明文传递密钥
3. **测试路由模式** - 先用测试域名验证，再应用到生产
4. **监控 Worker 日志** - 使用 `wrangler tail` 实时查看
5. **版本管理** - 保存每次部署的配置参数

---

## 🔐 安全建议

- ✅ API Token 使用最小权限原则
- ✅ 定期轮换 `FANGYU_SITE_SECRET`
- ✅ 使用 `wrangler secret` 管理敏感变量
- ✅ 不要将 Token 提交到版本控制
- ✅ 使用 fail-closed 模式提高安全性

---

**部署完成后，Worker 将自动拦截恶意流量并保护你的网站！** 🛡️

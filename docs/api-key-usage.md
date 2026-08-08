# API Key 使用指南

## 概述

Evercookie Defense System 使用 **API Key** 作为应用接入网关的身份凭证。每个应用（站点）在管理后台创建时会自动生成一对密钥：
- **site_id**（API Key）：公开凭证，用于 HTTP 请求中标识应用身份
- **app_secret**：私密密钥，用于请求签名验证

---

## 一、管理后台：创建应用与生成 API Key

### 1.1 创建应用

通过管理后台 API 创建应用时，系统会自动生成 API 凭证：

**接口：** `POST /v2/sites`

**请求示例：**
```json
{
  "name": "我的网站",
  "domain": "example.com",
  "alt_domains": ["www.example.com"],
  "access_mode": "adapter",
  "sdk_version": "2.0",
  "gateway_url": "https://gateway.example.com",
  "clock_stats_enabled": true,
  "log_retention_days": 30,
  "remark": "生产环境站点"
}
```

**响应示例：**
```json
{
  "code": "SUCCESS",
  "message": "操作成功",
  "data": {
    "id": 1,
    "site_id": "a1b2c3d4e5f6",           // ← API Key（公开）
    "app_secret": "48a8f2e3c1b5d7...",    // ← 签名密钥（私密，仅创建时返回）
    "name": "我的网站",
    "domain": "example.com",
    "status": "active",
    "created_at": "2026-08-07T10:00:00Z"
  }
}
```

> **⚠️ 重要提示：**
> - `app_secret` **仅在创建应用时返回一次**，请妥善保存
> - 丢失后需通过"轮换密钥"功能重新生成

---

### 1.2 轮换 API Key

如果密钥泄露或需要定期轮换，可调用轮换接口：

**接口：** `POST /v2/sites/{site_id}/rotate-key`

**响应：**
```json
{
  "code": "SUCCESS",
  "data": {
    "site_id": "a1b2c3d4e5f6",           // site_id 保持不变
    "app_secret": "新的签名密钥..."       // 新生成的密钥
  }
}
```

> **注意：** 轮换后旧密钥立即失效，需同步更新接入方配置

---

## 二、接入方：使用 API Key

### 2.1 配置凭证

将获取的凭证配置到接入方系统中：

#### Nginx 适配器配置
```nginx
# /etc/nginx/conf.d/fangyu.conf
location /fangyu-gateway/ {
    proxy_set_header X-App-Key "a1b2c3d4e5f6";      # site_id
    set $app_secret "48a8f2e3c1b5d7...";              # app_secret（用于 Lua 签名）
    # ...
}
```

#### WordPress 插件配置
```php
// wp-config.php 或插件设置
define('FANGYU_SITE_ID', 'a1b2c3d4e5f6');
define('FANGYU_APP_SECRET', '48a8f2e3c1b5d7...');
```

#### 环境变量（推荐）
```bash
# .env
FANGYU_SITE_ID=a1b2c3d4e5f6
FANGYU_APP_SECRET=48a8f2e3c1b5d7...
```

---

### 2.2 请求签名规范

网关要求关键接口（`/v2/decide*`、`/v2/sdk/*`）必须签名，防止画像伪造。

#### 签名步骤

1. **携带 API Key**（两种方式任选其一）：
   ```http
   # 方式 1：专用 Header
   X-App-Key: a1b2c3d4e5f6
   
   # 方式 2：Bearer Token
   Authorization: Bearer a1b2c3d4e5f6
   ```

2. **构造请求参数**（POST JSON Body）：
   ```json
   {
     "timestamp": 1691234567,
     "nonce": "random-uuid-v4",
     "fingerprint": "...",
     "ip": "1.2.3.4",
     "sign": "计算的签名值"
   }
   ```

3. **计算签名**：
   ```python
   # Python 示例
   import hmac
   import hashlib
   import time
   import uuid
   
   # 待签名参数（排除 sign 本身）
   params = {
       "timestamp": int(time.time()),
       "nonce": str(uuid.uuid4()),
       "fingerprint": "浏览器指纹",
       "ip": "访客 IP"
   }
   
   # 按 key 排序后拼接：key1=value1&key2=value2
   sign_payload = "&".join(
       f"{k}={v}" for k, v in sorted(params.items())
   )
   
   # HMAC-SHA256 签名
   app_secret = "48a8f2e3c1b5d7..."
   signature = hmac.new(
       app_secret.encode(),
       sign_payload.encode(),
       hashlib.sha256
   ).hexdigest()
   
   params["sign"] = signature
   ```

4. **发送请求**：
   ```python
   import requests
   
   response = requests.post(
       "https://gateway.example.com/v2/decide",
       headers={"X-App-Key": "a1b2c3d4e5f6"},
       json=params
   )
   ```

---

### 2.3 签名验证逻辑

网关验证流程（代码见 `gateway-api/src/interfaces/http/middleware/app_key.py:229-265`）：

1. **时间戳检查**：`timestamp` 必须在当前时间 ±300 秒窗口内
2. **Nonce 一次性校验**：同一 `nonce` 只能使用一次（Redis 防重放）
3. **HMAC 签名校验**：重新计算签名并与 `sign` 对比

**任一步骤失败返回：**
```json
{
  "code": "AUTH_UNAUTHENTICATED",
  "message": "API Key 无效或已失效",
  "request_id": "req-123"
}
```

> **安全设计：** 不区分具体失败原因（Key 错误/签名错误/重放），避免信息泄露

---

## 三、Redis 数据结构

### 3.1 正向索引（API Key → App ID）

**键位：** `fangyu:app_keys:{site_id}`

**值格式：**
```json
{
  "app_id": 1,
  "app_secret": "48a8f2e3c1b5d7..."
}
```

**用途：** 网关通过 `site_id` 快速反查 `app_id` 和 `app_secret`

---

### 3.2 反向索引（App ID → App Secret）

**键位：** `fangyu:app_secrets:{app_id}`

**值格式：** `48a8f2e3c1b5d7...`（纯字符串）

**用途：** 挑战（Challenge）令牌签发时，网关需根据 `app_id` 查询密钥

> **为什么需要反向索引？**
> - 多 Worker 部署下，处理 `/v2/challenge/verify` 的进程可能与 `/v2/decide` 不同
> - 正向键以 `site_id` 为后缀，无法按 `app_id` 检索
> - 仅靠本地缓存会导致挑战校验静默失败

---

## 四、常见问题

### Q1：app_secret 丢失了怎么办？
**A：** 调用 `/v2/sites/{site_id}/rotate-key` 接口重新生成，旧密钥立即失效。

### Q2：可以关闭签名验证吗？
**A：** 可临时关闭（`.env` 设置 `GATEWAY_SIGNATURE_REQUIRED=false`），但**强烈不推荐**：
- 关闭后任何人都能伪造访客画像（IP、UA、行为数据）
- 仅在接入方未完成签名改造时临时使用

### Q3：时间戳校验失败怎么办？
**A：** 确保接入方服务器时间与 NTP 同步，误差不超过 ±5 分钟。

### Q4：Nonce 重复导致请求失败？
**A：** 每次请求必须生成**新的** UUID，不能复用旧 nonce。

### Q5：创建应用时 app_secret 未记录？
**A：** 密钥仅在创建响应中返回一次，未保存需轮换密钥重新生成。

---

## 五、安全最佳实践

1. **密钥存储**
   - ✅ 使用环境变量或密钥管理服务（Vault、AWS Secrets Manager）
   - ❌ 禁止硬编码在代码或版本控制中

2. **密钥传输**
   - ✅ 仅通过 HTTPS 传输
   - ✅ 后端服务间通过内网传递

3. **密钥轮换**
   - 建议每 90 天轮换一次
   - 密钥泄露后立即轮换

4. **权限控制**
   - 管理后台创建应用需要 `app.write` 权限
   - 查看 API Key 详情需要 `app.read` 权限

5. **监控告警**
   - 监控 API Key 校验失败率（可能的攻击迹象）
   - 记录密钥轮换操作日志

---

## 六、代码参考

### 后端实现
- **生成逻辑：** `admin-api/src/application/services/app_service.py:79`
- **Redis 同步：** `admin-api/src/infrastructure/cache/app_key_sync.py:55-81`
- **签名验证：** `gateway-api/src/interfaces/http/middleware/app_key.py:229-265`

### 前端集成
- 浏览器 SDK 会自动处理签名逻辑，无需手动实现
- 服务端适配器需参考 `shared/src/fangyu_shared/utils/crypto.py` 实现签名算法

---

## 七、环境变量配置

在 `.env` 中配置 API Key 相关参数：

```bash
# ── Gateway API Key 校验（详见 .env.example:184-188） ──
GATEWAY_APP_KEY_REQUIRED=true          # 是否强制校验
GATEWAY_APP_KEY_HEADER=X-App-Key       # Header 名称
GATEWAY_SIGNATURE_REQUIRED=true        # 是否需要签名
GATEWAY_SIGNATURE_WINDOW=300           # 签名时间窗口（秒）

# ── Redis 键前缀（通常无需修改） ──
GATEWAY_APP_KEY_REDIS_PREFIX=fangyu:app_keys:
GATEWAY_APP_KEY_CACHE_TTL=60           # 本地缓存 TTL（秒）
```

---

**相关文档：**
- [环境变量配置说明](../.env.example)
- [签名算法实现](../shared/src/fangyu_shared/utils/crypto.py)
- [网关中间件源码](../gateway-api/src/interfaces/http/middleware/app_key.py)

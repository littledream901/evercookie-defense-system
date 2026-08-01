# V2 API 契约总览

**用途**: 明确 V1 兼容接口 + V2 新特性接口，为前后端联调提供权威规范

---

## 一、Gateway API（决策引擎）

### 1.1 V1 兼容接口

保留 V1 全部路由与请求/响应结构：

| 方法 | 路径 | 说明 | V2 实现文件 |
|------|------|------|-------------|
| POST | `/v1/decide` | 完整决策 | `gateway-api/src/interfaces/http/v1/decide.py`（薄适配层） |

### 1.2 V2 新增接口

| 方法 | 路径 | 说明 | 关键特性 |
|------|------|------|---------|
| POST | `/v2/decide` | 完整决策 | 支持缓存、精准规则、五级流水线 |
| POST | `/v2/decide/fast` | 快速决策 | 仅缓存 + 精准规则，P95 < 20ms |
| POST | `/v2/rule/test` | 规则沙箱 | 单条规则试运行，返回详细过程 |
| GET | `/health` | 健康检查 | Redis/MySQL/CH 状态 |
| GET | `/metrics` | Prometheus 指标 | - |

### 1.3 `/v2/decide` 请求示例

```json
{
  "request_id": "req_20260731_001",
  "app_id": "app_xxx",
  "site_id": "site_001",
  "device_id": "dev_yyy",
  "fingerprint": {
    "canvas": "...",
    "webgl": "...",
    "audio": "..."
  },
  "network": {
    "ip": "1.2.3.4",
    "user_agent": "...",
    "referer": "..."
  },
  "behavior": {
    "page_load_time": 1200,
    "mouse_events": 42
  },
  "timestamp": 1785478929000,
  "sign": "hmac_sha256_hex"
}
```

### 1.4 `/v2/decide` 响应示例

```json
{
  "code": "OK",
  "request_id": "req_20260731_001",
  "decision": {
    "dispatch_type": "money_page",
    "risk_score": 12,
    "cached": true,
    "precision_matched": false,
    "source": "cache"
  },
  "dispatch": {
    "target_url": "https://example.com/money",
    "method": "302"
  },
  "signals": [
    { "name": "ip_type", "value": "residential", "weight": 0 },
    { "name": "device_score", "value": 88, "weight": -10 }
  ],
  "timing": {
    "total_ms": 8,
    "cache_ms": 3,
    "profile_ms": 0,
    "match_ms": 0,
    "pipeline_ms": 0
  }
}
```

---

## 二、Admin API（管理后台）

### 2.1 V1 兼容接口（完全一致）

保留 V1 全部路由：
- `/v1/auth/*`（登录、刷新、注销）
- `/v1/users/*`
- `/v1/apps/*`
- `/v1/rules/*`
- `/v1/analytics/*`

### 2.2 V2 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v2/rules/versions/{app_id}` | 规则版本列表 |
| POST | `/v2/rules/versions/{app_id}/rollback` | 回滚到指定版本 |
| GET | `/v2/rules/templates` | 规则模板库 |
| POST | `/v2/rules/preview` | 规则效果预览（无需保存） |
| GET | `/v2/analytics/realtime` | 实时统计（10s 粒度） |

---

## 三、Worker（无对外接口）

Worker 是后台进程，无 HTTP 接口。仅通过 Redis Stream 消费。

**监控端点**：
- `GET /internal/health`：健康检查
- `GET /internal/metrics`：Prometheus 指标

---

## 四、统一响应格式

### 4.1 成功响应

```json
{
  "code": "OK",
  "data": { ... },
  "request_id": "req_xxx"
}
```

### 4.2 错误响应

```json
{
  "code": "APP_NOT_FOUND",
  "message": "应用 xxx 不存在",
  "details": {
    "resource_type": "app",
    "resource_id": "xxx"
  },
  "request_id": "req_xxx"
}
```

### 4.3 错误码约定

| 前缀 | 类别 | 示例 |
|------|------|------|
| `AUTH_*` | 认证/授权 | `AUTH_INVALID_TOKEN` |
| `PERM_*` | 权限 | `PERM_DENIED` |
| `VALID_*` | 参数校验 | `VALID_FIELD_REQUIRED` |
| `RES_*` | 资源 | `RES_NOT_FOUND` |
| `RULE_*` | 规则 | `RULE_INVALID_CONDITION` |
| `SIGN_*` | 签名 | `SIGN_MISMATCH` |
| `RATE_*` | 限流 | `RATE_LIMIT_EXCEEDED` |
| `INTERNAL_*` | 内部错误 | `INTERNAL_UNKNOWN` |

---

## 五、认证与签名

### 5.1 Admin API 认证

- 登录：`POST /v1/auth/login` → `access_token` + `refresh_token`
- 请求头：`Authorization: Bearer <access_token>`
- Token TTL：access 30min，refresh 7day

### 5.2 Gateway API 签名

- 算法：HMAC-SHA256
- 输入：按 key 字典序拼接的 `key=value&key=value`（值需 URL 编码）
- 密钥：站点级 `api_key`
- 输出：hex 编码
- 校验容差：时间戳 ± 5 分钟

---

## 六、限流策略

| 接口 | 限流方式 | 阈值 |
|------|---------|------|
| `/v2/decide/*` | 按 `site_id` + `client_ip` | 1000 req/min |
| `/v1/auth/login` | 按 `client_ip` | 10 req/min |
| Admin API 其他 | 按用户 | 300 req/min |

超限返回 `429 RATE_LIMIT_EXCEEDED`。

---

## 七、OpenAPI 规范

- Gateway API：`http://localhost:8000/docs`（Swagger UI）
- Admin API：`http://localhost:8001/docs`
- 导出 OpenAPI JSON：
  ```bash
  curl http://localhost:8000/openapi.json > docs/api/gateway_openapi.json
  curl http://localhost:8001/openapi.json > docs/api/admin_openapi.json
  ```

---

**文档结束**

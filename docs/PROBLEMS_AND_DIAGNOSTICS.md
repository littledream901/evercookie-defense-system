# 站点接入问题诊断速查手册

## 📖 快速索引

本文档提供站点接入常见问题的快速诊断和解决方案。

---

## 🔍 问题分类

### 1. 完全无流量（status: `no_data`）

#### 问题表现
- 近 N 小时无任何决策记录
- 站点列表显示「未检测」状态
- 诊断详情显示「无任何决策记录」

#### 可能原因及排查步骤

| 原因 | 排查方法 | 解决方案 |
|------|---------|---------|
| **埋码未部署** | 检查代码是否已上线 | 部署接入代码到生产环境 |
| **站点已停用** | 查看站点启用状态 | 在站点管理中重新启用 |
| **密钥错误** | 测试连通性接口 | 检查 `site_key` / `site_secret` 是否正确 |
| **签名验证失败** | 查看网关日志 `request_signature_rejected` | 修正签名算法实现 |
| **时钟偏差 > 5分钟** | 检查服务器时间 `date` | 同步服务器时钟 `ntpdate` |
| **网关不可达** | `curl` 测试网关地址 | 检查网络连接、防火墙规则 |
| **X-App-Key 错误** | 确认请求头中的值 | 使用站点的 `site_key` 而非 `site_id` |

#### 诊断命令

```bash
# 1. 检查服务器时间
date -u
# 应与 UTC 时间一致，误差不超过 5 分钟

# 2. 测试网关连通性
curl -v https://gateway.yourdomain.com/health

# 3. 模拟决策请求（检查签名）
curl -X POST https://gateway.yourdomain.com/v2/decide \
  -H "Content-Type: application/json" \
  -H "X-App-Key: site_abc123xyz" \
  -d '{
    "context": {
      "siteId": 42,
      "ingress": "test",
      "fingerprint": "test_fp",
      "userAgent": "curl/7.64.0",
      "visitUrl": "https://example.com/test"
    },
    "timestamp": 1234567890,
    "nonce": "test_nonce",
    "sign": "computed_hmac_sha256_signature"
  }'

# 4. 查看网关日志（如果有访问权限）
docker logs gateway-container | grep "request_signature_rejected"
```

---

### 2. 接入方式不一致（status: `error`）

#### 问题表现
- 诊断代码：`ingress_mismatch`
- 提示：「实测接入方式与站点配置不一致」

#### 原因分析

| 配置值 | 实测值 | 场景 | 解决方案 |
|--------|--------|------|---------|
| `adapter` | `sdk` | 前端直接调用，未经服务端 | 修改站点配置为 `sdk`，或移除前端 SDK |
| `sdk` | `adapter` | 部署了服务端适配器 | 修改站点配置为 `adapter` |
| `adapter` | `adapter, sdk` | 同时部署了服务端和客户端 | 确认是否有意，否则移除多余路径 |

#### 典型场景

**场景1：测试环境残留埋码**
```
问题：生产使用 Nginx-Lua，但测试环境的 SDK 代码未清理
表现：ingress_stats 显示 adapter (9800) + sdk (200)
解决：删除测试环境的 SDK 代码片段
```

**场景2：配置未同步更新**
```
问题：从 SDK 切换到 Nginx-Lua，但站点配置未修改
表现：站点配置 access_mode=sdk，实测全部来自 adapter
解决：更新站点配置为 adapter
```

---

### 3. 流量断档（status: `warning`）

#### 问题表现
- 诊断代码：`traffic_gap`
- 提示：「流量已中断 N 小时」

#### 排查清单

```bash
# 1. 确认站点是否正常运营
curl -I https://example.com
# 200 OK → 站点在线
# 无响应 → 站点已下线

# 2. 检查 Nginx 配置是否生效（Nginx-Lua 模式）
nginx -t
nginx -s reload

# 3. 检查 Lua 脚本是否存在
ls -la /etc/nginx/lua/fangyu/defense.lua

# 4. 查看 Nginx 错误日志
tail -f /var/log/nginx/error.log | grep fangyu

# 5. 检查 Worker 是否部署（CF Worker 模式）
wrangler deployments list

# 6. 检查 SDK 脚本是否可访问（SDK 模式）
curl -I https://gateway.yourdomain.com/sdk/sd-sdk.min.js
# 应返回 200 OK
```

#### 常见原因

| 原因 | 表现 | 解决方案 |
|------|------|---------|
| **站点下线** | 域名无法访问 | 重新启动站点或停用防护 |
| **Nginx 配置被覆盖** | 配置文件不包含 Lua 指令 | 重新添加 Lua 配置并 reload |
| **Lua 脚本丢失** | Nginx 日志报错 `cannot open` | 重新部署 `defense.lua` |
| **Worker 未部署** | CF 控制台无 Worker | `wrangler deploy` 重新部署 |
| **SDK 脚本 404** | 浏览器控制台报错 | 检查 CDN 或网关配置 |
| **网关故障** | 所有站点同时断流 | 检查网关服务状态 |

---

### 4. 高错误率（status: `warning`）

#### 问题表现
- 诊断代码：`high_risk_ratio`
- 提示：「N% 流量被判为高风险」

#### 场景分析

| hostile + suspicious 占比 | 场景 | 建议 |
|---------------------------|------|------|
| **> 80%** | 规则过严 / 测试流量污染 / 真实攻击 | 检查规则配置 |
| **50% - 80%** | 部分流量异常 | 查看访问日志，分析来源 |
| **< 50%** | 正常防护 | 无需处理 |

#### 排查步骤

```bash
# 1. 查看访问日志，分析高风险流量特征
# 在仪表盘 -> 访问日志 -> 筛选 verdict=hostile

# 2. 检查规则配置是否合理
# 例如：是否误判了正常用户的 User-Agent

# 3. 确认是否为测试流量
# 如果测试账号触发大量拦截，建议使用独立测试站点

# 4. 分析 IP 来源
# 如果来自数据中心 IP 段，可能是真实攻击
```

#### 常见误判场景

```yaml
场景1：过严的 User-Agent 规则
问题：拦截了所有移动端流量
原因：规则误配置为 "user_agent not_contains Mobile"
解决：修正规则条件

场景2：测试流量污染
问题：自动化测试脚本触发大量 hostile
原因：测试脚本使用固定指纹，被识别为自动化工具
解决：设置独立测试站点，排除测试流量

场景3：真实 DDoS 攻击
问题：短时间内大量不同 IP 的请求
特征：hostile_count 突增，unique_ips >> unique_fingerprints
解决：保持现有规则，攻击会被正确拦截
```

---

### 5. SDK 特有问题

#### 5.1 派生指纹占比过高（`sdk_derived_fingerprint`）

**问题**：`derived_count / total > 50%`

**原因**：
- SDK 脚本未真正执行
- 被 CSP（内容安全策略）阻止
- 被广告拦截器屏蔽
- `defer` / `async` 导致执行顺序错误

**排查**：
```html
<!-- ❌ 错误：加了 defer，内联调用先于 SDK 加载 -->
<script src="https://gateway/sdk/sd-sdk.min.js" defer></script>
<script>
  SdSdk.guard({...})  // 报错：SdSdk is not defined
</script>

<!-- ✅ 正确：不加 defer/async，同步加载 -->
<script src="https://gateway/sdk/sd-sdk.min.js"></script>
<script>
  SdSdk.guard({...})
</script>
```

**检查浏览器控制台**：
```javascript
// 打开浏览器控制台，检查错误
// 常见错误：
// 1. "SdSdk is not defined" → 脚本加载顺序错误
// 2. "Refused to load ... CSP" → 内容安全策略阻止
// 3. "Failed to fetch" → 网络连接问题
```

#### 5.2 无行为事件（`sdk_no_behavior`）

**问题**：`behavior_count == 0`

**原因**：
- 页面停留时间太短（< 1s）
- 用户立即跳转到其他页面
- SDK 配置关闭了行为采集

**解决**：
```javascript
// 检查 SDK 配置
SdSdk.guard({
  apiBase: '...',
  apiKey: '...',
  siteId: 42,
  // collectBehavior: false  // ← 如果设置为 false，不会采集行为
})
```

---

### 6. Adapter 特有问题

#### 6.1 IP 未透传（`adapter_single_ip`）

**问题**：`unique_ips <= 1 且 total > 20`

**原因**：适配器上报的是反向代理自身的 IP，而非真实访客 IP

**排查**：
```nginx
# Nginx-Lua 模式
# 检查 Lua 脚本如何获取客户端 IP

# ❌ 错误：直接使用 ngx.var.remote_addr
local client_ip = ngx.var.remote_addr  
-- 在反向代理后会获取到代理 IP

# ✅ 正确：优先读取 X-Forwarded-For
local client_ip = ngx.var.http_x_forwarded_for or 
                  ngx.var.http_x_real_ip or 
                  ngx.var.remote_addr
```

**检查上游代理配置**：
```nginx
# 上游 Nginx / Cloudflare 必须设置这些头
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP $remote_addr;
```

**验证**：
```bash
# 从外部访问站点，查看请求头
curl -H "X-Forwarded-For: 1.2.3.4" https://example.com
# 检查网关日志中记录的 IP 是否为 1.2.3.4
```

---

### 7. 签名验证失败

#### 问题表现
- 完全无流量（请求在网关鉴权阶段被拒绝）
- 网关日志显示 `401 Unauthorized`

#### 签名算法标准

```python
# Python 标准实现
import hmac
import hashlib
import json

def sign_request(site_secret, timestamp, nonce, context):
    # 1. context 按 key 排序后序列化（无空格）
    context_json = json.dumps(context, sort_keys=True, separators=(',', ':'))
    
    # 2. 拼接签名字符串
    sign_base = f"{timestamp}{nonce}{context_json}"
    
    # 3. HMAC-SHA256 签名
    signature = hmac.new(
        site_secret.encode('utf-8'),
        sign_base.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature

# 示例
site_secret = "your_site_secret"
timestamp = 1700000000
nonce = "abc123"
context = {
    "siteId": 42,
    "ingress": "adapter",
    "ip": "1.2.3.4",
    "userAgent": "Mozilla/5.0 ...",
    "visitUrl": "https://example.com/page"
}

sign = sign_request(site_secret, timestamp, nonce, context)
print(sign)  # 输出签名
```

#### 常见错误

| 错误 | 表现 | 正确做法 |
|------|------|---------|
| **JSON 序列化包含空格** | `{"key": "value"}` | `{"key":"value"}` |
| **JSON key 未排序** | `{"b":1,"a":2}` | `{"a":2,"b":1}` |
| **timestamp 未转字符串** | 拼接为 `1700000000abc123{...}` | 正确 ✓ |
| **编码不一致** | 用 GBK 编码 | 统一使用 UTF-8 |
| **site_secret 错误** | 使用了旧的 secret | 轮换后需更新 |

---

## 🛠️ 诊断工具

### 1. 批量健康检查脚本

```python
# 检查所有站点的接入健康度
import requests

API_BASE = "https://admin.yourdomain.com"
TOKEN = "your_access_token"

headers = {"Authorization": f"Bearer {TOKEN}"}

# 获取所有站点
sites = requests.get(f"{API_BASE}/api/v2/sites", headers=headers).json()
site_ids = [s["id"] for s in sites["items"]]

# 批量诊断
result = requests.post(
    f"{API_BASE}/api/v2/sites/batch-diagnostics",
    json={"site_ids": site_ids, "hours": 24},
    headers=headers
).json()

# 输出异常站点
for site in result["data"]:
    if site["status"] in ["error", "warning"]:
        print(f"[{site['status'].upper()}] {site['site_name']}: {site['primary_issue']}")
```

### 2. 连通性测试脚本

```bash
#!/bin/bash
# test-connection.sh

SITE_ID=42
API_BASE="https://admin.yourdomain.com"
TOKEN="your_access_token"

curl -X POST "${API_BASE}/api/v2/sites/${SITE_ID}/test-connection" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | jq '.data'
```

### 3. 实时监听首次流量

```javascript
// monitor-first-traffic.js
const SITE_ID = 42;
const API_BASE = 'https://admin.yourdomain.com';
const TOKEN = 'your_access_token';

async function checkTraffic() {
  const res = await fetch(
    `${API_BASE}/api/v2/sites/${SITE_ID}/integration-diagnostics?hours=1`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  const data = await res.json();
  
  if (data.data.total_requests > 0) {
    console.log('✅ 检测到首次流量！');
    console.log(`接入方式: ${data.data.ingress_stats[0].ingress}`);
    console.log(`请求数: ${data.data.total_requests}`);
    process.exit(0);
  } else {
    console.log('⏳ 等待流量中...');
  }
}

// 每5秒检测一次
setInterval(checkTraffic, 5000);
checkTraffic();
```

---

## 📞 技术支持

### 常见问题无法解决？

1. **查看网关日志**（如果有权限）
   ```bash
   docker logs -f gateway-container
   # 关注 request_signature_rejected / invalid_site_key 等日志
   ```

2. **在诊断页面测试连通性**
   - 进入站点列表 → 点击「接入」按钮
   - 切换到诊断 tab → 点击「测试连通性」
   - 根据返回的错误信息排查

3. **联系技术支持**
   - 提供站点 ID、错误截图、网关日志
   - 描述操作步骤和预期行为

---

## 📚 相关文档

- [接入诊断功能优化](./INTEGRATION_DIAGNOSTICS_OPTIMIZATION.md)
- [项目编码规范](../.trae/rules/project-rule.md)
- [API 文档](./api/) - 如有

---

**文档版本**：v1.0  
**最后更新**：2026-08-09  
**维护人员**：EverCookie Defense Team

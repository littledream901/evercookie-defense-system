# 关闭评分后仍被拦截的排查指南

## 核心问题

**关闭风险评分 ≠ 不再拦截**

风险评分只是决策流水线的**其中一个阶段**。即使关闭评分，访问仍可能被其他阶段拦截。

---

## 决策流水线顺序

访问请求会按以下顺序经过多个阶段（**任一阶段拦截即终止**）：

```
1. WHITELIST       - 白名单（命中直接放行）
2. CHALLENGE_PASS  - 挑战通行凭据（已通过验证则放行）
3. CLOCK           - 频控封禁（超限直接拦截）
4. HYBRID_LOOKUP   - 混合层查询（服务端预判）
5. CACHE           - 决策缓存（命中则返回缓存结果）
6. DECISION_RULE   - 决策规则匹配（⭐ 最常见的拦截原因）
7. THREAT_INTEL    - IP 威胁情报（恶意 IP 库）
8. SECURITY        - 基础安全检查（地理围栏/Tor/黑名单）
9. RISK_SCORING    - 风险评分（⭐ 您关闭的是这个）
10. DEFAULT        - 兜底策略（app 默认或系统默认）
```

**关闭风险评分只是跳过第 9 步**，前面 1-8 步仍然会执行！

---

## 如何确定真正的拦截原因

### 步骤 1：查看访问日志的关键字段

在 `/logs/access` 中找到被拦截的记录，重点查看：

| 字段 | 说明 | 示例 |
|------|------|------|
| **decided_by** | 👈 **最重要！真正的拦截来源** | `decision_rule` / `scoring` / `security` |
| **decided_stage** | 在哪个阶段被拦截 | `decision_rule` / `risk_scoring` / `threat_intel` |
| **reason** | 拦截的具体原因 | `datacenter;new_device` / `rule:高风险IP拦截` |
| **verdict** | 裁决结果 | `trusted` / `suspect` / `hostile` |
| **mechanism** | 处置方式 | `pass` / `challenge` / `deny` |

### 步骤 2：根据 `decided_by` 判断原因

#### ✅ 如果 `decided_by` = `scoring`
- **说明**：确实是风险评分导致的拦截
- **原因**：配置未生效或查看的是历史数据
- **解决**：等待 30 秒后刷新，查看最新日志

#### ⚠️ 如果 `decided_by` = `decision_rule`（最常见）
- **说明**：被**决策规则**拦截，与评分无关
- **原因**：您在 `/settings/rules` 中配置了拦截规则
- **解决**：
  1. 前往 `/settings/rules` 查看规则列表
  2. 找到 `reason` 中提到的规则名称
  3. 禁用或修改该规则

#### ⚠️ 如果 `decided_by` = `clock_ban` 或 `clock_rate_limit`
- **说明**：被**频控/封禁**拦截
- **原因**：访问频率超过限制或已被封禁
- **解决**：
  1. 前往 `/settings/clock` 调整频控配置
  2. 或在 `/settings/allowlist` 添加白名单

#### ⚠️ 如果 `decided_by` = `threat_intel`
- **说明**：IP 在**威胁情报库**中
- **原因**：IP 被标记为恶意
- **解决**：如果是误报，添加到白名单

#### ⚠️ 如果 `decided_by` = `security`
- **说明**：触发了**基础安全检查**
- **原因**：可能是 Tor 节点、地理围栏、或黑名单
- **解决**：检查 `/settings/security` 配置

---

## 常见误解

### ❌ 误解：关闭评分 = 不再拦截任何流量
**正确理解**：关闭评分只是跳过风险评分阶段，其他 8 个阶段仍会执行。

### ❌ 误解：`reason` 字段 = 拦截原因
**正确理解**：`reason` 只是原因描述，真正的拦截来源看 **`decided_by`** 字段。

### ❌ 误解：看到 `datacenter.new_device` 就是评分导致的
**正确理解**：必须同时满足：
- `decided_by` = `scoring` ✅
- `decided_stage` = `risk_scoring` ✅
- `reason` 包含评分器名称 ✅

---

## 实际案例分析

### 案例 1：决策规则拦截（最常见）

```json
{
  "decided_by": "decision_rule",        // 👈 被决策规则拦截
  "decided_stage": "decision_rule",
  "reason": "decision_rule:数据中心IP拦截",
  "verdict": "hostile",
  "mechanism": "deny"
}
```

**分析**：虽然 `reason` 提到数据中心，但 `decided_by` 是 `decision_rule`，说明是您配置的规则导致的拦截，**与评分无关**。

**解决**：前往 `/settings/rules` 找到名为"数据中心IP拦截"的规则并禁用。

---

### 案例 2：评分拦截（关闭评分后不应该出现）

```json
{
  "decided_by": "scoring",              // 👈 被评分拦截
  "decided_stage": "risk_scoring",
  "reason": "datacenter;new_device",
  "score": 60.0,
  "verdict": "suspect",
  "mechanism": "challenge"
}
```

**分析**：确实是评分导致的拦截。

**解决**：
1. 检查是否是历史数据（看时间戳）
2. 等待 30 秒后刷新
3. 检查 Redis 配置：`GET fangyu:scoring:{site_id}`

---

### 案例 3：频控封禁

```json
{
  "decided_by": "clock_ban",            // 👈 被频控封禁
  "decided_stage": "clock",
  "reason": "ip_banned",
  "verdict": "hostile",
  "mechanism": "not_found"
}
```

**分析**：IP 因为访问过快被封禁。

**解决**：调整频控配置或添加白名单。

---

## 快速排查步骤

1. **打开访问日志** `/logs/access`
2. **找到被拦截的记录**（`verdict` = `suspect` 或 `hostile`）
3. **查看 `decided_by` 字段**
4. **根据上面的案例分析对应处理**

---

## 如果确认是评分拦截但已关闭

如果 `decided_by` = `scoring` 且您确认已关闭评分，请检查：

1. ✅ **检查时间戳**：日志是否早于配置变更时间？
2. ✅ **等待 30 秒**：配置缓存需要时间生效
3. ✅ **检查站点 ID**：配置的站点与日志的站点是否一致？
4. ✅ **检查 Redis**：
   ```bash
   redis-cli
   GET fangyu:scoring:{your_site_id}
   ```
   应该看到 `"enabled": false`

---

## 相关文档

- 决策流水线：[decision_service.py](../gateway-api/src/application/services/decision_service.py)
- 决策来源枚举：[disposition.py:23-37](../gateway-api/src/domain/decision/disposition.py)
- 评分配置缓存：[scoring_config_cache.py](../gateway-api/src/infrastructure/cache/scoring_config_cache.py)

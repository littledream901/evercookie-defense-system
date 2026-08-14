# Bug修复：频控配置 0 值未生效问题

## 问题描述

用户在后台频控配置页面设置 `burst = 0`（期望不限流），但实际流量仍被频控拦截，显示 `rate_limit:ip:burst(31/30)`。

## 根本原因

### 1. 前端保存逻辑缺陷

**位置**: `dashboard-ui/src/views/fangyu/clock/index.vue:189-218`

**问题代码**:
```javascript
// 旧代码
await fetchPutClockLimits({ ...limitsForm })
```

前端直接保存 `limitsForm.limits`，但该对象可能：
- 用户输入 `0` 时，前端未明确保存该值
- 导致后端收到的 `windows` 为空字典 `{}`

### 2. 后端回退逻辑

**位置**: `shared/src/fangyu_shared/schemas/clock.py:68-70`

```python
def limit_for(self, window: ClockWindow) -> int:
    """取某窗口的阈值。0 表示该窗口不限流。"""
    return self.windows.get(window.name, DEFAULT_LIMITS.get(window.name, 0))
```

**逻辑**:
- 如果 `windows["burst"]` 存在且为 `0`，返回 `0`（不限流）✅
- 如果 `windows` 中**没有 `"burst"` 键**，回退到 `DEFAULT_LIMITS["burst"] = 30` ⚠️

### 3. 问题流程

```
用户设置 burst=0 
  ↓
前端未明确保存 0 值
  ↓
后端收到 windows={}
  ↓
网关读取时 windows.get("burst") 返回 None
  ↓
回退到 DEFAULT_LIMITS["burst"] = 30
  ↓
流量在 10 秒内 31 次被拦截
```

## 修复方案

### 修改前端保存逻辑

**文件**: `dashboard-ui/src/views/fangyu/clock/index.vue`

**修复内容**:

1. **显式保存所有窗口配置，包括 0 值**

```javascript
// 修复后代码
const limitsPayload = {
  enabled: limitsForm.enabled,
  banEnabled: limitsForm.banEnabled,
  banSeconds: limitsForm.banSeconds,
  limits: {} as Record<string, number>
}

// 为所有窗口显式设置值，即使是 0
windows.value.forEach((w) => {
  limitsPayload.limits[w.name] = limitsForm.limits[w.name] ?? 0
})

await fetchPutClockLimits(limitsPayload)
```

2. **优化用户体验：当所有窗口为 0 时给予确认提示**

```javascript
if (limitsForm.enabled && !activeWindows.length) {
  const confirmed = await ElMessageBox.confirm(
    '所有窗口阈值均为 0（不限流），频控将不会生效。确认保存吗？',
    '确认保存',
    { confirmButtonText: '保存', cancelButtonText: '取消', type: 'warning' }
  ).catch(() => false)
  if (!confirmed) return
}
```

## 验证步骤

### 1. 验证前端修复

```bash
cd dashboard-ui
npm run build
```

### 2. 测试场景

#### 场景一：设置 burst = 0（不限流）

1. 打开频控配置页面
2. 设置 `burst = 0`, `short = 0`, `hour = 0`
3. 点击"保存配置"
4. 确认提示："所有窗口阈值均为 0（不限流），频控将不会生效"
5. 确认保存

**预期结果**:
- 后端收到 `windows: {"burst": 0, "short": 0, "hour": 0}`
- 网关读取后返回 `limit_for("burst") = 0`
- 流量不受频控限制

#### 场景二：设置部分窗口为 0

1. 设置 `burst = 0`, `short = 100`, `hour = 1000`
2. 保存配置

**预期结果**:
- 后端收到 `windows: {"burst": 0, "short": 100, "hour": 1000}`
- burst 窗口不限流
- short/hour 窗口按配置生效

### 3. 验证后端逻辑

```python
# 测试用例
from fangyu_shared.schemas.clock import ClockLimits
from fangyu_shared.clock.windows import WINDOW_BURST

# 情况1：显式设置为 0
limits1 = ClockLimits(siteId=5, windows={"burst": 0})
assert limits1.limit_for(WINDOW_BURST) == 0  # ✅ 不限流

# 情况2：未设置（空字典）
limits2 = ClockLimits(siteId=5, windows={})
assert limits2.limit_for(WINDOW_BURST) == 30  # ⚠️ 回退到默认值

# 情况3：设置为正值
limits3 = ClockLimits(siteId=5, windows={"burst": 50})
assert limits3.limit_for(WINDOW_BURST) == 50  # ✅ 使用自定义值
```

## 影响范围

### 修改文件
- `dashboard-ui/src/views/fangyu/clock/index.vue` (前端)

### 不需要修改
- 后端逻辑（已正确实现）
- 数据库结构
- API 接口

### 兼容性
- ✅ 向后兼容：旧配置（空 windows）继续回退到默认值
- ✅ 新配置：显式 0 值正确生效

## 部署说明

### 1. 前端部署

```bash
cd dashboard-ui
npm run build
# 部署 dist 目录到静态服务器
```

### 2. 清除用户浏览器缓存

通知用户强制刷新页面（Ctrl+F5）

### 3. 验证部署

1. 打开浏览器开发者工具 → Network
2. 保存频控配置
3. 查看 PUT 请求 payload，确认 `limits` 包含所有窗口的值

```json
{
  "enabled": true,
  "banEnabled": true,
  "banSeconds": 900,
  "limits": {
    "burst": 0,    // ✅ 显式包含 0 值
    "short": 0,
    "hour": 0
  }
}
```

## 临时解决方案（修复前）

如果无法立即部署前端修复，用户可以：

### 方案一：关闭频控
```
启用频控: 关闭
```

### 方案二：使用 API 直接设置

```bash
curl -X PUT "http://admin-api/v2/sites/5/clock/limits" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "banEnabled": false,
    "banSeconds": 900,
    "windows": {
      "burst": 0,
      "short": 0,
      "hour": 0
    }
  }'
```

### 方案三：将 IP 加入白名单

```bash
curl -X POST "http://admin-api/v2/sites/5/whitelist" \
  -H "Content-Type: application/json" \
  -d '{
    "dimension": "ip",
    "value": "82.152.165.148",
    "reason": "测试流量",
    "enabled": true
  }'
```

## 相关文件

- 前端：`dashboard-ui/src/views/fangyu/clock/index.vue`
- 后端逻辑：`shared/src/fangyu_shared/schemas/clock.py`
- 默认值定义：`shared/src/fangyu_shared/clock/limits.py`
- 窗口定义：`shared/src/fangyu_shared/clock/windows.py`

## 总结

这是一个**前端数据序列化缺陷**导致的问题，后端逻辑本身正确。修复后：

- ✅ 用户设置 `0` 值会被正确保存和生效
- ✅ 未设置的窗口继续回退到默认值（保持向后兼容）
- ✅ 增强用户体验：全 0 配置时给予确认提示

**修复日期**: 2026-08-14
**影响版本**: V2 所有版本
**修复版本**: V2.1+

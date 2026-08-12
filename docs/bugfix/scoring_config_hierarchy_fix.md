# 评分配置层级缺陷修复

## 🐛 问题描述

### Bug 1：网关配置回退逻辑缺失
**问题**：站点配置缺失时，直接使用硬编码默认值（`enabled: True`），跳过了全局配置的回退。

**影响**：
- 用户在前端关闭全局评分
- 站点 4 没有独立配置
- 网关读取站点 4 配置失败后，使用硬编码默认值 `enabled: True`
- **评分仍然开启，用户的关闭操作无效**

### Bug 2：前端只支持全局配置
**问题**：前端评分页面硬编码只能配置全局（`site_id: 0`），无法为单个站点配置。

**影响**：
- 无法为特定站点单独关闭评分
- 无法为特定站点自定义阈值和权重
- 多站点场景下配置管理困难

### Bug 3：配置优先级不完整
**设计缺陷**：
- ❌ **当前逻辑**：站点配置 → 系统默认值（跳过全局）
- ✅ **正确逻辑**：站点配置 → 全局配置 → 系统默认值

---

## ✅ 修复方案

### 修复 1：网关添加全局配置回退

**文件**：`gateway-api/src/infrastructure/cache/scoring_config_cache.py`

**修改内容**：
1. 新增 `_load_with_fallback()` 方法
2. 实现三级配置回退：站点配置 → 全局配置 → 系统默认值
3. 站点配置缺失时，自动读取全局配置（`site_id: 0`）

**核心逻辑**：
```python
async def _load_with_fallback(self, site_id: int) -> ScoringConfig:
    """站点配置缺失时，回退到全局配置（site_id=0），最后才用系统默认值。
    
    配置层级：站点配置 > 全局配置 > 系统默认值
    """
    if site_id == 0:
        # 已经是全局配置，直接返回系统默认值
        return self._default_config()
    
    # 尝试读取全局配置
    try:
        global_raw = await self._redis.get(f"{_KEY_PREFIX}:0")
        if global_raw:
            global_data = orjson.loads(global_raw)
            return self._parse(global_data)
    except Exception as exc:
        _logger.warning("scoring_global_config_fallback_failed", site_id=site_id, error=str(exc))
    
    # 全局配置也不存在，返回系统默认值
    return self._default_config()
```

**效果**：
- ✅ 用户关闭全局评分后，所有未单独配置的站点自动继承
- ✅ 站点可以独立配置覆盖全局设置
- ✅ 配置层级清晰，行为符合预期

---

### 修复 2：前端支持站点级配置

**文件**：`dashboard-ui/src/views/fangyu/scoring/index.vue`

**修改内容**：

#### 1. 添加配置范围切换器
```vue
<ElSegmented v-model="configScope" :options="scopeOptions" @change="onScopeChange" />
```

选项：
- **全局配置**：作用于所有未单独配置的站点
- **当前站点**：仅作用于当前选中的站点

#### 2. 动态调用对应 API
```typescript
// 加载配置
const cfg = configScope.value === 'global'
  ? await fetchGetGlobalScoringConfig()
  : await fetchGetScoringConfig(currentSiteId.value!)

// 保存配置
if (configScope.value === 'global') {
  await fetchPutGlobalScoringConfig({...})
} else {
  await fetchPutScoringConfig(currentSiteId.value!, {...})
}

// 重置配置
if (configScope.value === 'global') {
  await fetchResetGlobalScoringConfig()
} else {
  await fetchResetScoringConfig(currentSiteId.value!)
}
```

#### 3. 添加状态提示
- 站点模式下未选择站点：显示警告提示
- 站点未配置：显示"将继承全局配置"提示
- 配置保存后创建站点独立配置

**效果**：
- ✅ 支持全局配置和站点配置切换
- ✅ 可以为单个站点独立配置评分规则
- ✅ 提示信息清晰，用户不会误操作

---

## 📊 配置层级示例

### 场景 1：只配置全局
```
Redis 键：
  fangyu:scoring:0 → { enabled: false }

站点 4 读取流程：
  1. 查询 fangyu:scoring:4 → 不存在
  2. 回退查询 fangyu:scoring:0 → 找到，enabled: false
  3. 站点 4 评分关闭 ✅
```

### 场景 2：站点覆盖全局
```
Redis 键：
  fangyu:scoring:0 → { enabled: false, threshold_hostile: 75 }
  fangyu:scoring:4 → { enabled: true, threshold_hostile: 90 }

站点 4 读取流程：
  1. 查询 fangyu:scoring:4 → 找到
  2. 使用站点配置：enabled: true, threshold_hostile: 90
  3. 站点 4 评分开启，阈值 90 ✅
```

### 场景 3：全局和站点都不存在
```
Redis 键：
  （无任何配置）

站点 4 读取流程：
  1. 查询 fangyu:scoring:4 → 不存在
  2. 回退查询 fangyu:scoring:0 → 不存在
  3. 使用系统默认值：enabled: true, threshold_hostile: 75
  4. 站点 4 评分开启（默认行为）✅
```

---

## 🧪 测试验证

### 测试 1：全局配置生效
1. 在前端切换到"全局配置"
2. 关闭评分开关，保存
3. 等待 30 秒（配置缓存过期）
4. 访问站点 4（未单独配置）
5. **预期**：`decided_by` 不是 `scoring`，评分被跳过

### 测试 2：站点配置覆盖
1. 在前端切换到"当前站点"（站点 4）
2. 开启评分，阈值设为 90
3. 保存配置
4. 等待 30 秒
5. 访问站点 4
6. **预期**：评分开启，阈值 90 生效

### 测试 3：站点配置删除后回退
1. 在前端"当前站点"模式点击"恢复默认"
2. 站点配置被删除
3. 等待 30 秒
4. 访问站点 4
5. **预期**：继承全局配置（如果全局关闭，则站点也关闭）

---

## 📝 注意事项

### 1. 配置缓存 TTL
- 网关侧配置缓存：**30 秒**
- 修改配置后需等待最多 30 秒才完全生效

### 2. 站点选择
- 前端"当前站点"模式从 URL 参数读取站点 ID（`?site_id=4` 或路由参数）
- 未传递站点 ID 时，保存按钮被禁用

### 3. 重置操作
- **全局配置**：重置为系统默认值
- **站点配置**：删除站点配置，回退到全局配置

### 4. 向后兼容
- 修复前创建的配置仍然有效
- 只有新的读取请求会应用回退逻辑
- 建议在全局配置中明确设置期望行为

---

## 🎯 用户操作指南

### 关闭所有站点的评分
1. 前端切换到"全局配置"
2. 关闭评分开关
3. 保存
4. 等待 30 秒
5. **所有未单独配置的站点自动继承，评分关闭**

### 单独开启某个站点的评分
1. 前端切换到"当前站点"
2. 选择目标站点（如站点 4）
3. 开启评分开关，调整阈值
4. 保存
5. **该站点评分开启，其他站点保持全局配置**

### 让站点回归全局配置
1. 前端切换到"当前站点"
2. 选择目标站点
3. 点击"恢复默认"
4. **站点配置被删除，自动使用全局配置**

---

## 🔍 排查命令

### 查看 Redis 配置
```bash
# 全局配置
redis-cli GET "fangyu:scoring:0"

# 站点 4 配置
redis-cli GET "fangyu:scoring:4"
```

### 查看网关日志
```bash
# 配置回退日志
grep "scoring_global_config_fallback" gateway.log

# 配置加载失败
grep "scoring_config_fetch_failed" gateway.log
```

---

## 📚 相关文件

### 后端
- `gateway-api/src/infrastructure/cache/scoring_config_cache.py` - 配置读取和回退逻辑
- `admin-api/src/infrastructure/scoring_sync.py` - 配置写入 Redis
- `admin-api/src/interfaces/http/v2/scoring.py` - API 路由

### 前端
- `dashboard-ui/src/views/fangyu/scoring/index.vue` - 评分配置页面
- `dashboard-ui/src/api/scoring.ts` - API 调用方法

### 文档
- `docs/troubleshooting/why_still_blocked_after_disable_scoring.md` - 排查指南
- `docs/troubleshooting/scoring_reason_after_disabled.md` - 原因分析

---

## ✅ 修复完成

- [x] 网关配置回退逻辑实现
- [x] 前端站点配置支持
- [x] 配置层级清晰化
- [x] 用户操作指南完善
- [x] 文档更新

**修复后，用户关闭全局评分将正确作用于所有未单独配置的站点。**

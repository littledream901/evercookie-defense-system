# 评分配置页面 - 标签页架构重构

## 概述

将评分配置页面从单一作用域模式重构为**标签页架构**，支持全局配置和各站点独立配置，增强继承关系展示。

---

## 核心特性

### 1️⃣ 双层配置架构

```
全局配置（默认值）
  ├─ 站点 A 配置（继承并覆盖）
  ├─ 站点 B 配置（继承并覆盖）
  └─ 站点 C 配置（继承并覆盖）
```

#### 标签页设计
- **全局配置标签页**：设置所有站点的默认评分规则
- **站点配置标签页**：每个站点一个标签，可覆盖全局配置

#### 继承逻辑
- 站点配置**未保存过**时 → 完全继承全局配置
- 站点配置**已保存**时 → 使用站点独立配置
- 点击"恢复默认"按钮 → 删除站点配置，重新继承全局配置

---

### 2️⃣ 增强的继承关系展示

#### 📊 全局配置视图
```vue
<ElAlert type="info">
  此配置为所有站点的默认规则。
  各站点可在其专属标签页中覆盖此配置。
</ElAlert>
```

#### 📊 站点配置视图（继承状态）
```vue
<ElAlert type="success">
  当前使用全局配置（继承）
  <ElButton @click="loadConfig(siteId, true)">
    创建站点独立配置
  </ElButton>
</ElAlert>
```

#### 📊 站点配置视图（独立状态）
```vue
<ElAlert type="warning">
  当前使用站点独立配置
  <ElButton @click="resetConfig">恢复为全局配置</ElButton>
</ElAlert>

<!-- 表单顶部展示继承的全局配置 -->
<ElCard class="global-inherit-card">
  <template #header>
    继承自全局配置
    <ElButton @click="globalDrawerVisible = true">
      查看完整全局配置
    </ElButton>
  </template>
  <ElDescriptions :column="2" size="small">
    <ElDescriptionsItem label="评分开关">
      {{ globalConfig.enabled ? '开启' : '关闭' }}
    </ElDescriptionsItem>
    <ElDescriptionsItem label="可疑阈值">
      {{ globalConfig.threshold_suspect }}
    </ElDescriptionsItem>
    <ElDescriptionsItem label="敌对阈值">
      {{ globalConfig.threshold_hostile }}
    </ElDescriptionsItem>
  </ElDescriptions>
</ElCard>
```

---

### 3️⃣ 全局配置侧边抽屉

站点配置页面提供**全局配置只读视图抽屉**：

```typescript
const globalDrawerVisible = ref(false)
const globalConfig = ref<Api.Fangyu.ScoringConfig | null>(null)

// 加载全局配置用于参考
const loadGlobalConfigForReference = async () => {
  const res = await fetchGetGlobalScoringConfig()
  globalConfig.value = res
}
```

**交互流程**：
1. 用户在站点 A 标签页编辑配置
2. 点击"查看完整全局配置"按钮
3. 右侧弹出抽屉，展示全局配置的所有字段
4. 用户可对比站点配置与全局配置的差异

---

## 技术实现

### API 调用映射

| 标签页类型 | 加载配置 | 保存配置 | 恢复默认 |
|----------|---------|---------|---------|
| **全局配置** | `fetchGetGlobalScoringConfig()` | `fetchPutGlobalScoringConfig(data)` | `fetchResetGlobalScoringConfig()` |
| **站点配置** | `fetchGetScoringConfig(siteId)` | `fetchPutScoringConfig(siteId, data)` | `fetchResetScoringConfig(siteId)` |

### 状态管理

```typescript
// 标签页状态
const activeTab = ref<'global' | number>('global')  // 'global' 或站点 ID
const siteList = ref<SiteOption[]>([])
const siteListLoading = ref(false)

// 配置状态
const configForm = reactive<Api.Fangyu.ScoringConfig>(createScoringConfig())
const configLoading = ref(false)
const hasCustomConfig = ref(false)  // 当前站点是否有独立配置

// 全局配置参考
const globalConfig = ref<Api.Fangyu.ScoringConfig | null>(null)
const globalDrawerVisible = ref(false)
```

### 配置加载逻辑

```typescript
const loadConfig = async (target: 'global' | number, forceCreate = false) => {
  configLoading.value = true
  try {
    if (target === 'global') {
      // 加载全局配置
      const res = await fetchGetGlobalScoringConfig()
      Object.assign(configForm, res)
      hasCustomConfig.value = false
    } else {
      // 加载站点配置
      try {
        const res = await fetchGetScoringConfig(target)
        Object.assign(configForm, res)
        hasCustomConfig.value = true
      } catch (err: any) {
        if (err.response?.status === 404) {
          // 站点未保存过配置，继承全局配置
          if (!forceCreate) {
            const globalRes = await fetchGetGlobalScoringConfig()
            Object.assign(configForm, globalRes)
            hasCustomConfig.value = false
          } else {
            // 用户点击"创建独立配置"，加载全局配置作为初始值
            const globalRes = await fetchGetGlobalScoringConfig()
            Object.assign(configForm, globalRes)
            hasCustomConfig.value = true
          }
        }
      }
    }
  } finally {
    configLoading.value = false
  }
}
```

---

## UI 交互流程

### 场景 1：用户切换到未配置的站点
```
1. 点击"站点 A"标签
2. 后端返回 404（无独立配置）
3. 前端加载全局配置并展示
4. 显示提示："当前使用全局配置（继承）"
5. 提供按钮："创建站点独立配置"
```

### 场景 2：用户创建站点独立配置
```
1. 点击"创建站点独立配置"按钮
2. 表单从只读变为可编辑
3. 顶部提示改为："当前使用站点独立配置"
4. 用户修改参数后点击"保存"
5. 调用 fetchPutScoringConfig(siteId, data)
6. 保存成功后，hasCustomConfig = true
```

### 场景 3：用户恢复为全局配置
```
1. 点击"恢复为全局配置"按钮
2. 弹出确认对话框
3. 确认后调用 fetchResetScoringConfig(siteId)
4. 后端删除站点配置记录
5. 前端重新加载，显示继承的全局配置
6. hasCustomConfig = false
```

### 场景 4：用户查看全局配置对比
```
1. 在站点标签页，点击"查看完整全局配置"
2. 右侧弹出抽屉，展示全局配置的所有字段
3. 用户可对比当前站点配置与全局配置的差异
4. 关闭抽屉，继续编辑站点配置
```

---

## 视觉设计要点

### 标签页样式
```scss
.scoring-tabs {
  .el-tabs__item {
    &.is-active {
      color: #C4612F;  // terracotta 主题色
      font-weight: 500;
    }
  }
}
```

### 继承状态卡片
```vue
<!-- 继承状态 - 成功色 -->
<ElAlert type="success" :closable="false">
  <template #title>
    当前使用全局配置（继承）
  </template>
</ElAlert>

<!-- 独立配置 - 警告色 -->
<ElAlert type="warning" :closable="false">
  <template #title>
    当前使用站点独立配置
  </template>
</ElAlert>
```

### 全局配置参考卡片
```vue
<ElCard shadow="never" class="mb-4 bg-orange-50 border-orange-200">
  <template #header>
    <div class="flex items-center justify-between">
      <span class="text-sm text-orange-700">
        📋 继承自全局配置
      </span>
      <ElButton link type="primary" @click="globalDrawerVisible = true">
        查看完整全局配置 →
      </ElButton>
    </div>
  </template>
  <ElDescriptions :column="2" size="small" border>
    <!-- 关键字段展示 -->
  </ElDescriptions>
</ElCard>
```

---

## 后端 API 契约

### 全局配置
```http
GET  /api/v2/fangyu/scoring/config/global
PUT  /api/v2/fangyu/scoring/config/global
POST /api/v2/fangyu/scoring/config/global/reset
```

### 站点配置
```http
GET    /api/v2/fangyu/scoring/config/{site_id}  # 404 表示无独立配置
PUT    /api/v2/fangyu/scoring/config/{site_id}
DELETE /api/v2/fangyu/scoring/config/{site_id}  # 或 POST /reset
```

**关键约定**：
- 站点配置 404 → 前端应继承全局配置
- `PUT` 站点配置 → 创建或更新独立配置
- `DELETE` 站点配置 → 删除独立配置，后续请求返回 404

---

## 测试要点

### ✅ 功能测试
- [ ] 全局配置的保存和重置
- [ ] 站点配置的创建、保存、重置
- [ ] 站点未配置时正确继承全局配置
- [ ] 标签页切换时配置正确加载
- [ ] 全局配置抽屉正确展示

### ✅ 边界测试
- [ ] 后端返回 404 时的兜底逻辑
- [ ] 站点列表为空时的 UI 表现
- [ ] 并发切换标签页时的 loading 状态
- [ ] 恢复默认时的二次确认

### ✅ 视觉测试
- [ ] 继承状态提示的颜色和图标
- [ ] 全局配置参考卡片的样式
- [ ] 标签页激活态的主题色
- [ ] 抽屉的宽度和滚动行为

---

## 文件清单

| 文件路径 | 说明 |
|---------|------|
| `dashboard-ui/src/views/fangyu/scoring/index.vue` | 评分配置页面主组件 |
| `dashboard-ui/src/api/scoring.ts` | 评分配置 API |
| `dashboard-ui/src/api/apps.ts` | 站点列表 API |
| `docs/features/scoring-tabbed-ui.md` | 本文档 |

---

## 后续优化方向

1. **配置差异高亮**：在站点配置视图中，用颜色高亮显示与全局配置不同的字段
2. **批量操作**：支持"将站点 A 配置复制到站点 B"
3. **配置历史**：记录配置变更历史，支持回滚
4. **权限控制**：细粒度的全局/站点配置编辑权限

---

最后更新：2026-08-12

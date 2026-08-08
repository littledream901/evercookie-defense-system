# SDK 诊断页面优化

## 🐛 修复的问题

### 1. 内容重叠 Bug ✅

**问题描述**：
- 页面标题区域与错误提示框发生重叠
- 筛选器按钮组在窄屏下换行导致布局错乱

**根本原因**：
- 使用 `flex-wrap` 导致控件在空间不足时换行
- 错误提示框没有被包含在同一个容器中，导致定位异常

**修复方案**：
```vue
<!-- 修复前 -->
<div class="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-2">
  <div>标题</div>
  <div>筛选器</div>
</div>
<ElAlert v-if="loadError" ... />

<!-- 修复后 -->
<div class="mb-3 flex shrink-0 flex-col gap-3">
  <div class="flex items-start justify-between gap-2">
    <div class="flex-1">标题</div>
    <div class="flex flex-shrink-0 items-center gap-2">筛选器</div>
  </div>
  <ElAlert v-if="loadError" ... />
</div>
```

**关键改动**：
- ✅ 外层改为 `flex-col`（垂直布局），将标题行和错误提示框放在同一容器
- ✅ 标题区域使用 `flex-1`，允许文本区域伸缩
- ✅ 筛选器区域使用 `flex-shrink-0`，防止按钮被压缩
- ✅ 移除 `flex-wrap`，保证控件始终在一行

---

### 2. 增加应用级筛选 ✅

**功能需求**：
- 用户可以先选择应用，然后只看该应用下的站点
- 支持"全部应用"选项，显示所有站点

**实现方案**：

#### A. 数据结构调整
```typescript
// 修复前
const appOptions = ref<{ label: string; value: number }[]>([])

// 修复后
const selectedAppId = ref<number>()  // 当前选中的应用
const allSites = ref<{ 
  label: string; 
  value: number; 
  app_id: number; 
  app_name: string 
}[]>([])
const appGroupOptions = ref<{ label: string; value: number }[]>([])
```

#### B. 应用筛选逻辑
```typescript
// 根据应用筛选站点
const filteredSiteOptions = computed(() => {
  if (!selectedAppId.value) return allSites.value
  return allSites.value.filter((s) => s.app_id === selectedAppId.value)
})
```

#### C. 应用切换处理
```typescript
const onAppChange = () => {
  // 切换应用时，如果当前选中的站点不属于新应用，清空站点选择
  if (siteId.value && selectedAppId.value) {
    const currentSite = allSites.value.find((s) => s.value === siteId.value)
    if (currentSite && currentSite.app_id !== selectedAppId.value) {
      siteId.value = undefined
      data.value = null
    }
  }
}
```

#### D. 应用列表构建
```typescript
// 构建应用分组选项（去重）
const appMap = new Map<number, string>()
items.forEach((i) => {
  if (i.app_id && !appMap.has(i.app_id)) {
    appMap.set(i.app_id, i.app_name || `应用 ${i.app_id}`)
  }
})
appGroupOptions.value = Array.from(appMap.entries()).map(([id, name]) => ({
  label: name,
  value: id
}))
```

#### E. UI 调整
```vue
<ElSelect
  v-model="selectedAppId"
  placeholder="全部应用"
  clearable
  style="width: 180px"
  :loading="appLoading"
  @change="onAppChange"
>
  <ElOption v-for="o in appGroupOptions" :key="o.value" :label="o.label" :value="o.value" />
</ElSelect>

<ElSelect
  v-model="siteId"
  placeholder="选择站点"
  style="width: 200px"
  :loading="appLoading"
  @change="onSiteChange"
>
  <ElOption v-for="o in filteredSiteOptions" :key="o.value" :label="o.label" :value="o.value" />
</ElSelect>
```

---

## 📊 优化效果

### 修复前
❌ 标题与错误提示重叠  
❌ 筛选器在窄屏下换行错乱  
❌ 只能逐个查找站点，无法按应用分组  
❌ 站点列表过长（100+ 站点）难以查找  

### 修复后
✅ 布局清晰，不再重叠  
✅ 筛选器始终在一行，不换行  
✅ 支持应用级筛选，快速定位  
✅ 站点下拉框显示应用归属，例如 `站点A (应用1)`  
✅ 支持"全部应用"选项，灵活切换  

---

## 🎯 用户体验提升

### 使用场景 1：快速定位某个应用的站点
```
1. 用户选择"电商平台"应用
2. 站点下拉框自动过滤，只显示该应用下的站点
3. 用户选择"主站"进行诊断
```

### 使用场景 2：浏览所有站点
```
1. 用户不选择应用（或清空应用选择）
2. 站点下拉框显示所有站点
3. 站点名称后显示应用归属，例如 `主站 (电商平台)`
```

### 使用场景 3：切换应用时的智能处理
```
1. 用户当前查看"电商平台 - 主站"
2. 用户切换到"CRM系统"应用
3. 系统自动清空站点选择（因为"主站"不属于"CRM系统"）
4. 避免出现不一致的状态
```

---

## 🔧 技术细节

### 1. 布局修复
- **问题**：`flex-wrap` + 绝对定位错误提示导致重叠
- **方案**：改为 `flex-col` 垂直布局，将所有顶部元素放在同一容器
- **效果**：错误提示与标题自然垂直排列，不会重叠

### 2. 应用筛选
- **数据源**：复用站点列表 API，从 `app_id` 和 `app_name` 字段提取应用信息
- **去重逻辑**：使用 `Map` 去重，避免重复的应用选项
- **筛选逻辑**：使用 `computed` 响应式计算，自动更新站点列表

### 3. 状态同步
- **问题**：切换应用后，如果当前站点不属于新应用，会出现不一致
- **方案**：在 `onAppChange` 中检查并清空不匹配的站点
- **效果**：保证数据一致性，避免用户困惑

### 4. 性能优化
- **站点数量上限**：保持 100（后端 API 限制）
- **原因**：后端 `page_size` 参数限制 `le=100`，前端需遵守此限制
- **优化**：增加应用筛选后，用户可以分组查看，不需要一次加载所有站点

---

## 📁 修改文件

- `dashboard-ui/src/views/fangyu/sdk-diagnostics/index.vue`
  - 修复布局重叠问题（+5 行，-10 行）
  - 增加应用筛选功能（+40 行）
  - 优化站点加载逻辑（+20 行）

---

## ✅ 测试建议

### 1. 布局测试
- [ ] 页面正常打开，标题与筛选器不重叠
- [ ] 错误提示正确显示在标题下方
- [ ] 调整浏览器窗口大小，布局始终正常

### 2. 应用筛选测试
- [ ] 应用下拉框正确显示所有应用
- [ ] 选择应用后，站点下拉框正确过滤
- [ ] 清空应用选择，站点下拉框显示所有站点
- [ ] 站点名称正确显示应用归属

### 3. 切换测试
- [ ] 选择应用 A 的站点，然后切换到应用 B，站点选择自动清空
- [ ] 选择应用 A 的站点，然后清空应用，站点选择保持不变（因为站点仍在列表中）

### 4. 边界测试
- [ ] 没有站点时，正确显示"请先选择站点"
- [ ] 站点列表加载失败时，正确显示错误提示
- [ ] 应用列表为空时，应用下拉框为空（正常）

---

## 🎉 总结

**修复内容**：
1. ✅ 修复内容重叠 Bug（布局问题）
2. ✅ 增加应用级筛选功能（用户体验提升）

**优化效果**：
- 布局更清晰，不再重叠
- 筛选更高效，支持应用分组
- 用户体验更好，快速定位站点

**状态**：✅ 已完成，无 TypeScript 错误

---

**优化日期**：2026-08-09  
**优化人员**：AI Assistant  
**版本**：V3 双层架构

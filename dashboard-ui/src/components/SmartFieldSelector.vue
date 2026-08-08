<!-- 智能字段选择器 -->
<template>
  <div class="smart-field-selector">
    <!-- 搜索框 -->
    <div class="selector-search">
      <ElInput
        v-model="searchKeyword"
        placeholder="搜索字段（支持中英文关键词）"
        clearable
        :prefix-icon="Search"
        @input="handleSearch"
      />
    </div>

    <!-- 常用字段快捷选择 -->
    <div v-if="!searchKeyword && frequentFields.length > 0" class="frequent-fields">
      <div class="section-title">
        <ElIcon><Star /></ElIcon>
        <span>常用字段</span>
      </div>
      <div class="field-chips">
        <ElTag
          v-for="field in frequentFields"
          :key="field.key"
          class="field-chip"
          effect="plain"
          @click="selectField(field.key)"
        >
          <span class="field-chip__label">{{ field.label }}</span>
          <span class="field-chip__key">{{ field.key }}</span>
        </ElTag>
      </div>
    </div>

    <!-- 搜索结果 -->
    <div v-if="searchKeyword && searchResults.length > 0" class="search-results">
      <div class="section-title">
        <ElIcon><Search /></ElIcon>
        <span>搜索结果（{{ searchResults.length }}）</span>
      </div>
      <div class="field-list">
        <div
          v-for="field in searchResults"
          :key="field.key"
          class="field-card"
          @click="selectField(field.key)"
        >
          <div class="field-card__header">
            <span class="field-card__label">{{ field.label }}</span>
            <ElTag size="small" type="info" effect="plain">{{ field.category }}</ElTag>
          </div>
          <div class="field-card__key">{{ field.key }}</div>
          <div class="field-card__hint">{{ field.hint }}</div>
        </div>
      </div>
    </div>

    <!-- 无搜索结果 -->
    <ElEmpty
      v-if="searchKeyword && searchResults.length === 0"
      description="未找到匹配的字段"
      :image-size="80"
    />

    <!-- 分组字段展示 -->
    <div v-if="!searchKeyword" class="field-groups">
      <ElCollapse v-model="activeGroups" accordion>
        <ElCollapseItem
          v-for="group in fieldGroups"
          :key="group.name"
          :name="group.name"
        >
          <template #title>
            <div class="group-title">
              <ElIcon :size="16">
                <component :is="group.icon" />
              </ElIcon>
              <span>{{ group.label }}</span>
              <ElTag size="small" type="info" effect="plain" class="ml-2">
                {{ group.fields.length }}
              </ElTag>
            </div>
          </template>
          <div class="field-list">
            <div
              v-for="field in group.fields"
              :key="field.key"
              class="field-card"
              @click="selectField(field.key)"
            >
              <div class="field-card__header">
                <span class="field-card__label">{{ field.label }}</span>
                <ElTag
                  v-if="field.frequency === 'high'"
                  size="small"
                  type="warning"
                  effect="plain"
                >
                  常用
                </ElTag>
              </div>
              <div class="field-card__key">{{ field.key }}</div>
              <div class="field-card__hint">{{ field.hint }}</div>
              <div v-if="field.examples && field.examples.length > 0" class="field-card__examples">
                <span class="examples-label">示例：</span>
                <code v-for="(ex, i) in field.examples.slice(0, 3)" :key="i" class="example-value">
                  {{ formatExample(ex) }}
                </code>
              </div>
            </div>
          </div>
        </ElCollapseItem>
      </ElCollapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Search, Star, Location, Histogram, Lock, Flag, Warning, Monitor, DataAnalysis, Connection, TrendCharts, Compass } from '@element-plus/icons-vue'
import { ALL_FIELDS, getFieldsByCategory } from '@/constants/fieldMetadata'

// ========== Props & Emits ==========
interface Props {
  modelValue?: string
  excludeFields?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  excludeFields: () => []
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'select': [fieldKey: string, metadata: any]
}>()

// ========== State ==========
const searchKeyword = ref('')
const activeGroups = ref<string[]>(['common'])

// 常用字段（frequency === 'high'）
const frequentFields = computed(() => {
  return Object.keys(ALL_FIELDS)
    .filter(key => !props.excludeFields.includes(key))
    .map(key => ({ key, ...ALL_FIELDS[key] }))
    .filter(f => f.frequency === 'high')
    .slice(0, 10)
})

// 字段分组配置
const fieldGroups = computed(() => {
  const groups = [
    { name: 'common', label: '常用字段', icon: Star, category: '常用字段' },
    { name: 'crawler', label: '爬虫识别', icon: Monitor, category: '爬虫识别' },
    { name: 'geo', label: '地理位置', icon: Location, category: '地理位置' },
    { name: 'security', label: '网络安全', icon: Lock, category: '网络安全' },
    { name: 'ip_profile', label: 'IP 画像', icon: DataAnalysis, category: 'IP画像' },
    { name: 'ua_parse', label: 'UA 解析', icon: Compass, category: 'UA解析' },
    { name: 'request', label: '请求属性', icon: Connection, category: '请求属性' },
    { name: 'risk', label: '风险评分', icon: Warning, category: '风险评分' },
    { name: 'behavior', label: '行为分析', icon: TrendCharts, category: '行为分析' },
    { name: 'threat', label: '威胁情报', icon: Flag, category: '威胁情报' },
    { name: 'custom', label: '自定义字段', icon: Histogram, category: '自定义字段' }
  ]

  return groups.map(g => ({
    ...g,
    fields: getFieldsByCategory(g.category)
      .filter(key => !props.excludeFields.includes(key))
      .map(key => ({ key, ...ALL_FIELDS[key] }))
  })).filter(g => g.fields.length > 0)
})

// 搜索结果
const searchResults = computed(() => {
  if (!searchKeyword.value.trim()) return []

  const keyword = searchKeyword.value.toLowerCase().trim()
  return Object.keys(ALL_FIELDS)
    .filter(key => !props.excludeFields.includes(key))
    .map(key => ({ key, ...ALL_FIELDS[key] }))
    .filter(field => {
      return (
        field.label.toLowerCase().includes(keyword) ||
        field.key.toLowerCase().includes(keyword) ||
        field.hint.toLowerCase().includes(keyword) ||
        field.category.toLowerCase().includes(keyword)
      )
    })
    .slice(0, 20)
})

// ========== Methods ==========
function handleSearch() {
  // 搜索时自动展开第一个分组
  if (searchKeyword.value && searchResults.value.length > 0) {
    activeGroups.value = []
  }
}

function selectField(fieldKey: string) {
  const metadata = ALL_FIELDS[fieldKey]
  emit('update:modelValue', fieldKey)
  emit('select', fieldKey, metadata)
}

function formatExample(value: any): string {
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (value === null) return 'null'
  return String(value)
}

// ========== Lifecycle ==========
onMounted(() => {
  // 默认展开常用字段分组
  activeGroups.value = ['common']
})
</script>

<style scoped lang="scss">
.smart-field-selector {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 600px;
  overflow-y: auto;
}

.selector-search {
  position: sticky;
  top: 0;
  background: var(--el-bg-color);
  z-index: 10;
  padding-bottom: 8px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin-bottom: 12px;

  .el-icon {
    color: var(--el-color-primary);
  }
}

// ========== 常用字段快捷选择 ==========
.frequent-fields {
  .field-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .field-chip {
    cursor: pointer;
    padding: 8px 12px;
    border-radius: 6px;
    transition: all 0.2s;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
      border-color: var(--el-color-primary);
    }

    &__label {
      font-size: 13px;
      font-weight: 500;
      color: var(--el-text-color-primary);
    }

    &__key {
      font-size: 11px;
      font-family: 'Monaco', 'Consolas', monospace;
      color: var(--el-text-color-secondary);
    }
  }
}

// ========== 字段列表 ==========
.field-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-card {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-bg-color);

  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }

  &__label {
    font-size: 14px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }

  &__key {
    font-size: 12px;
    font-family: 'Monaco', 'Consolas', monospace;
    color: var(--el-color-primary);
    margin-bottom: 6px;
  }

  &__hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.5;
  }

  &__examples {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    flex-wrap: wrap;

    .examples-label {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }

    .example-value {
      font-size: 11px;
      padding: 2px 6px;
      background: var(--el-fill-color-light);
      border-radius: 3px;
      color: var(--el-text-color-regular);
    }
  }
}

// ========== 分组折叠面板 ==========
.field-groups {
  :deep(.el-collapse) {
    border: none;
  }

  :deep(.el-collapse-item) {
    margin-bottom: 8px;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    overflow: hidden;
  }

  :deep(.el-collapse-item__header) {
    background: var(--el-fill-color-blank);
    padding: 12px 16px;
    border-bottom: none;
  }

  :deep(.el-collapse-item__wrap) {
    border-bottom: none;
  }

  :deep(.el-collapse-item__content) {
    padding: 12px 16px;
    background: var(--el-bg-color);
  }

  .group-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

// ========== 搜索结果 ==========
.search-results {
  animation: fadeIn 0.2s;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

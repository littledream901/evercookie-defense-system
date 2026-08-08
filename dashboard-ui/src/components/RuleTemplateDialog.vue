<!-- 规则模板选择对话框 -->
<template>
  <ElDialog
    v-model="visible"
    title="选择规则模板"
    width="900px"
    destroy-on-close
    @close="handleClose"
  >
    <div class="template-dialog">
      <!-- 搜索栏 -->
      <div class="search-bar">
        <ElInput
          v-model="searchKeyword"
          placeholder="搜索模板（名称、描述、标签）"
          clearable
          :prefix-icon="Search"
        />
        <ElSpace>
          <ElButton :icon="Star" @click="showFrequentOnly = !showFrequentOnly">
            {{ showFrequentOnly ? '显示全部' : '仅常用' }}
          </ElButton>
          <ElButton :icon="Refresh" @click="resetFilters">重置筛选</ElButton>
        </ElSpace>
      </div>

      <!-- 分类标签 -->
      <div class="category-tabs">
        <ElRadioGroup v-model="activeCategory" size="small">
          <ElRadioButton label="">全部 ({{ totalCount }})</ElRadioButton>
          <ElRadioButton
            v-for="cat in categories"
            :key="cat.name"
            :label="cat.name"
          >
            {{ cat.name }} ({{ cat.count }})
          </ElRadioButton>
        </ElRadioGroup>
      </div>

      <!-- 模板列表 -->
      <ElScrollbar max-height="500px" class="template-list-container">
        <div v-if="filteredTemplates.length === 0" class="empty-state">
          <ElEmpty description="未找到匹配的模板" :image-size="100" />
        </div>
        <div v-else class="template-list">
          <div
            v-for="template in filteredTemplates"
            :key="template.id"
            class="template-card"
            :class="{ 'template-card--selected': selectedTemplate?.id === template.id }"
            @click="selectTemplate(template)"
          >
            <!-- 卡片头部 -->
            <div class="template-card__header">
              <div class="template-card__title-row">
                <span class="template-card__name">{{ template.name }}</span>
                <div class="template-card__badges">
                  <ElTag
                    v-if="template.frequency === 'high'"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    常用
                  </ElTag>
                  <ElTag
                    size="small"
                    :type="getPriorityColor(template.priority)"
                    effect="plain"
                  >
                    {{ getPriorityLabel(template.priority) }}
                  </ElTag>
                  <ElTag
                    v-if="template.riskLevel && template.riskLevel !== 'low'"
                    size="small"
                    :type="getRiskColor(template.riskLevel)"
                    effect="plain"
                  >
                    {{ getRiskLabel(template.riskLevel) }}
                  </ElTag>
                </div>
              </div>
              <div class="template-card__category">{{ template.category }}</div>
            </div>

            <!-- 描述 -->
            <div class="template-card__description">{{ template.description }}</div>

            <!-- 条件预览 -->
            <div class="template-card__conditions">
              <div class="conditions-title">
                <ElIcon><Filter /></ElIcon>
                <span>匹配条件（{{ template.matchAll ? 'AND' : 'OR' }}）</span>
              </div>
              <div class="conditions-list">
                <code
                  v-for="(cond, i) in template.conditions.slice(0, 3)"
                  :key="i"
                  class="condition-item"
                >
                  {{ formatCondition(cond) }}
                </code>
                <span v-if="template.conditions.length > 3" class="condition-more">
                  +{{ template.conditions.length - 3 }} 个条件
                </span>
              </div>
            </div>

            <!-- 处置动作 -->
            <div class="template-card__disposition">
              <div class="disposition-item">
                <span class="disposition-label">匹配时：</span>
                <ElTag :type="getDispositionColor(template.onMatch.mechanism)" size="small">
                  {{ getDispositionLabel(template.onMatch.mechanism) }}
                </ElTag>
                <span class="disposition-ttl">TTL: {{ formatTTL(template.onMatch.ttlSeconds) }}</span>
              </div>
            </div>

            <!-- 标签 -->
            <div v-if="template.tags && template.tags.length > 0" class="template-card__tags">
              <ElTag
                v-for="tag in template.tags"
                :key="tag"
                size="small"
                effect="plain"
                class="tag-item"
              >
                {{ tag }}
              </ElTag>
            </div>

            <!-- 选中标记 -->
            <div v-if="selectedTemplate?.id === template.id" class="template-card__selected-mark">
              <ElIcon><Check /></ElIcon>
            </div>
          </div>
        </div>
      </ElScrollbar>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <div class="footer-tip">
          <ElIcon><InfoFilled /></ElIcon>
          <span>选择模板后，将自动填充规则条件和处置动作，您可以继续编辑调整</span>
        </div>
        <ElSpace>
          <ElButton @click="handleClose">取消</ElButton>
          <ElButton type="primary" :disabled="!selectedTemplate" @click="handleConfirm">
            应用模板
          </ElButton>
        </ElSpace>
      </div>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, Star, Refresh, Filter, InfoFilled, Check } from '@element-plus/icons-vue'
import {
  RULE_TEMPLATES,
  getTemplateCategories,
  searchTemplates,
  getFrequentTemplates,
  type RuleTemplate
} from '@/constants/ruleTemplates'
import { getFieldLabel } from '@/constants/fieldMetadata'

// ========== Props & Emits ==========
interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'select': [template: RuleTemplate]
}>()

// ========== State ==========
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const searchKeyword = ref('')
const activeCategory = ref('')
const showFrequentOnly = ref(false)
const selectedTemplate = ref<RuleTemplate | null>(null)

// ========== Computed ==========
// 分类统计
const categories = computed(() => {
  const cats = getTemplateCategories()
  return cats.map(name => ({
    name,
    count: RULE_TEMPLATES.filter(t => t.category === name).length
  }))
})

const totalCount = computed(() => RULE_TEMPLATES.length)

// 过滤后的模板
const filteredTemplates = computed(() => {
  let result = RULE_TEMPLATES

  // 搜索关键词
  if (searchKeyword.value.trim()) {
    result = searchTemplates(searchKeyword.value)
  }

  // 分类筛选
  if (activeCategory.value) {
    result = result.filter(t => t.category === activeCategory.value)
  }

  // 仅常用
  if (showFrequentOnly.value) {
    result = result.filter(t => t.frequency === 'high')
  }

  return result
})

// ========== Methods ==========
function selectTemplate(template: RuleTemplate) {
  selectedTemplate.value = template
}

function handleConfirm() {
  if (selectedTemplate.value) {
    emit('select', selectedTemplate.value)
    handleClose()
  }
}

function handleClose() {
  visible.value = false
  // 延迟重置状态，避免关闭动画异常
  setTimeout(() => {
    searchKeyword.value = ''
    activeCategory.value = ''
    showFrequentOnly.value = false
    selectedTemplate.value = null
  }, 300)
}

function resetFilters() {
  searchKeyword.value = ''
  activeCategory.value = ''
  showFrequentOnly.value = false
}

function formatCondition(cond: any): string {
  const fieldLabel = getFieldLabel(cond.field) || cond.field
  // 使用纯中文描述，与 OPERATOR_LABELS 保持一致
  const operatorMap: Record<string, string> = {
    eq: '等于',
    neq: '不等于',
    gt: '大于',
    gte: '大于等于',
    lt: '小于',
    lte: '小于等于',
    in: '在列表中',
    not_in: '不在列表中',
    in_ci: '在列表中(忽略大小写)',
    not_in_ci: '不在列表中(忽略大小写)',
    contains: '包含',
    not_contains: '不包含',
    startswith: '开头是',
    starts_with: '开头是',
    endswith: '结尾是',
    ends_with: '结尾是',
    regex: '正则匹配',
    cidr_in: '在CIDR段内',
    cidr_list_in: '在CIDR列表中',
    cidr_list_not_in: '不在CIDR列表中',
    asn_in: 'ASN在列表中',
    asn_not_in: 'ASN不在列表中'
  }
  const op = operatorMap[cond.operator] || cond.operator
  const value = formatValue(cond.value)
  return `${fieldLabel} ${op} ${value}`
}

function formatValue(val: any): string {
  if (val === '__NULL__') return '空'
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  if (Array.isArray(val)) return `[${val.join(', ')}]`
  return String(val)
}

function formatTTL(seconds: number): string {
  if (seconds === 0) return '不缓存'
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时`
  return `${Math.floor(seconds / 86400)}天`
}

function getPriorityLabel(priority: string): string {
  const map: Record<string, string> = {
    critical: '紧急',
    high: '高',
    normal: '普通',
    low: '低'
  }
  return map[priority] || priority
}

function getPriorityColor(priority: string): string {
  const map: Record<string, string> = {
    critical: 'danger',
    high: 'warning',
    normal: 'info',
    low: 'info'
  }
  return map[priority] || 'info'
}

function getRiskLabel(risk: string): string {
  const map: Record<string, string> = {
    high: '高风险',
    medium: '中风险',
    low: '低风险'
  }
  return map[risk] || risk
}

function getRiskColor(risk: string): 'danger' | 'warning' | 'info' | 'success' | 'primary' {
  const map: Record<string, 'danger' | 'warning' | 'info' | 'success' | 'primary'> = {
    high: 'danger',
    medium: 'warning',
    low: 'success'
  }
  return map[risk] || 'info'
}

function getDispositionLabel(mechanism: string): string {
  const map: Record<string, string> = {
    allow: '放行',
    challenge: '挑战',
    block: '拦截',
    serve_alt: '替代内容',
    redirect: '重定向',
    rate_limit: '限流'
  }
  return map[mechanism] || mechanism
}

function getDispositionColor(mechanism: string): 'danger' | 'warning' | 'info' | 'success' | 'primary' {
  const map: Record<string, 'danger' | 'warning' | 'info' | 'success' | 'primary'> = {
    allow: 'success',
    challenge: 'warning',
    block: 'danger',
    serve_alt: 'info',
    redirect: 'info',
    rate_limit: 'warning'
  }
  return map[mechanism] || 'info'
}
</script>

<style scoped lang="scss">
.template-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

// ========== 搜索栏 ==========
.search-bar {
  display: flex;
  gap: 12px;
  align-items: center;

  .el-input {
    flex: 1;
  }
}

// ========== 分类标签 ==========
.category-tabs {
  :deep(.el-radio-group) {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
}

// ========== 模板列表 ==========
.template-list-container {
  margin-top: 8px;
}

.template-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 12px;
  padding: 4px;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
}

// ========== 模板卡片 ==========
.template-card {
  position: relative;
  padding: 16px;
  border: 2px solid var(--el-border-color-lighter);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-bg-color);

  &:hover {
    border-color: var(--el-color-primary);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
  }

  &--selected {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    box-shadow: 0 4px 12px rgba(var(--el-color-primary-rgb), 0.2);
  }

  &__header {
    margin-bottom: 12px;
  }

  &__title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }

  &__name {
    font-size: 15px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  &__badges {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }

  &__category {
    font-size: 12px;
    color: var(--el-color-primary);
    font-weight: 500;
  }

  &__description {
    font-size: 13px;
    color: var(--el-text-color-secondary);
    line-height: 1.6;
    margin-bottom: 12px;
  }

  &__conditions {
    margin-bottom: 12px;
    padding: 10px;
    background: var(--el-fill-color-light);
    border-radius: 6px;

    .conditions-title {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 500;
      color: var(--el-text-color-regular);
      margin-bottom: 8px;

      .el-icon {
        color: var(--el-color-primary);
      }
    }

    .conditions-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .condition-item {
      font-size: 11px;
      padding: 4px 8px;
      background: var(--el-bg-color);
      border-radius: 4px;
      color: var(--el-text-color-regular);
      border: 1px solid var(--el-border-color-lighter);
    }

    .condition-more {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
      padding-left: 8px;
    }
  }

  &__disposition {
    margin-bottom: 12px;

    .disposition-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
    }

    .disposition-label {
      color: var(--el-text-color-secondary);
    }

    .disposition-ttl {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }
  }

  &__tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;

    .tag-item {
      font-size: 11px;
    }
  }

  &__selected-mark {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 24px;
    height: 24px;
    background: var(--el-color-primary);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 14px;
  }
}

// ========== 对话框底部 ==========
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  .footer-tip {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    flex: 1;

    .el-icon {
      color: var(--el-color-info);
      flex-shrink: 0;
    }
  }
}
</style>
